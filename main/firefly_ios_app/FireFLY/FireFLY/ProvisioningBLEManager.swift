//
//  ProvisioningBLEManager.swift
//  FireFLY
//
//  Created by MacBook Pro on 5/10/26.
//

import Combine
import CoreBluetooth
import Foundation

struct DiscoveredBLEDevice: Identifiable, Equatable {
    let id: UUID
    let name: String
    let rssi: Int
    let advertisedServices: [String]
    let isLikelyProvisioningDevice: Bool
    fileprivate let peripheral: CBPeripheral

    var detailText: String {
        if !advertisedServices.isEmpty {
            return advertisedServices.joined(separator: ", ")
        }

        return id.uuidString
    }

    var signalText: String {
        "\(rssi) dBm"
    }

    static func == (lhs: DiscoveredBLEDevice, rhs: DiscoveredBLEDevice) -> Bool {
        lhs.id == rhs.id &&
        lhs.name == rhs.name &&
        lhs.rssi == rhs.rssi &&
        lhs.advertisedServices == rhs.advertisedServices &&
        lhs.isLikelyProvisioningDevice == rhs.isLikelyProvisioningDevice
    }
}

final class ProvisioningBLEManager: NSObject, ObservableObject {
    // Prototype BLE contract from the repo's NimBLE scratch example:
    // service AB00, writeable credential characteristic AB01.
    // AB01 accepts one JSON payload containing SSID, password, and API key.
    private static let provisioningServiceUUID = CBUUID(string: "AB00")
    private static let combinedCredentialCharacteristicUUID = CBUUID(string: "AB01")
    private static let ssidCharacteristicUUID = CBUUID(string: "AB02")
    private static let passwordCharacteristicUUID = CBUUID(string: "AB03")
    private static let commandCharacteristicUUID = CBUUID(string: "AB04")

    @Published private(set) var devices: [DiscoveredBLEDevice] = []
    @Published private(set) var selectedDeviceID: UUID?
    @Published private(set) var isScanning = false
    @Published private(set) var canSendCredentials = false
    @Published private(set) var isBluetoothReady = false
    @Published private(set) var bluetoothStateMessage = "Bluetooth is starting."
    @Published private(set) var statusMessage = "Scan for an ESP32 device."

    private var centralManager: CBCentralManager!
    private var peripheralsByID: [UUID: CBPeripheral] = [:]
    private var connectedPeripheral: CBPeripheral?

    private var combinedCredentialCharacteristic: CBCharacteristic?
    private var ssidCharacteristic: CBCharacteristic?
    private var passwordCharacteristic: CBCharacteristic?
    private var commandCharacteristic: CBCharacteristic?

    private var pendingServiceDiscoveries = Set<String>()
    private var writeQueue: [WriteRequest] = []
    private var activeWrite: WriteRequest?
    private var writeCompletion: (() -> Void)?
    private var pendingDisconnectStatusMessage: String?
    private var sentCompletionMessage = "Credentials sent."

    override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }

    func startScanning() {
        guard centralManager.state == .poweredOn else {
            statusMessage = bluetoothStateMessage
            return
        }

        devices.removeAll()
        peripheralsByID.removeAll()
        isScanning = true
        statusMessage = "Scanning for ESP32."

        centralManager.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
    }

    func stopScanning() {
        centralManager.stopScan()
        isScanning = false
        if devices.isEmpty {
            statusMessage = "Scan stopped."
        }
    }

    func connect(to device: DiscoveredBLEDevice) {
        stopScanning()
        resetProvisioningCharacteristics()

        let peripheral = device.peripheral
        selectedDeviceID = device.id
        connectedPeripheral = peripheral
        peripheral.delegate = self

        statusMessage = "Connecting to \(device.name)."
        centralManager.connect(peripheral, options: nil)
    }

    @discardableResult
    func sendCredentials(
        ssid: String,
        password: String,
        apiKey: String,
        onSent: (() -> Void)? = nil
    ) -> Bool {
        let trimmedSSID = ssid.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)

        if let validationMessage = ProvisioningCredentialValidator.validationMessage(
            ssid: trimmedSSID,
            password: password,
            apiKey: trimmedAPIKey
        ) {
            statusMessage = validationMessage
            return false
        }

        guard let peripheral = connectedPeripheral else {
            statusMessage = "Connect to an ESP32 first."
            return false
        }

        guard let combinedCharacteristic = combinedCredentialCharacteristic else {
            statusMessage = "Connected, but no API key credential channel was found."
            return false
        }

        writeQueue.removeAll()
        activeWrite = nil
        writeCompletion = nil
        sentCompletionMessage = "Credentials sent to \(peripheral.displayName)."

        do {
            let payloadData = try ProvisioningCredentialValidator.payloadData(
                ssid: trimmedSSID,
                password: password,
                apiKey: trimmedAPIKey
            )

            guard queueWrite(payloadData, to: combinedCharacteristic, on: peripheral) else {
                statusMessage = "Credential channel is not writeable."
                return false
            }
        } catch {
            statusMessage = error.localizedDescription
            return false
        }

        writeCompletion = onSent
        canSendCredentials = false
        statusMessage = "Sending credentials."
        processNextWrite()
        return true
    }

    private func resetProvisioningCharacteristics() {
        canSendCredentials = false
        combinedCredentialCharacteristic = nil
        ssidCharacteristic = nil
        passwordCharacteristic = nil
        commandCharacteristic = nil
        pendingServiceDiscoveries.removeAll()
        writeQueue.removeAll()
        activeWrite = nil
        writeCompletion = nil
    }

    private func updateReadyState() {
        canSendCredentials = connectedPeripheral != nil && combinedCredentialCharacteristic != nil

        if canSendCredentials {
            statusMessage = "Connected. Send credentials."
        } else if connectedPeripheral != nil && ssidCharacteristic != nil && passwordCharacteristic != nil {
            statusMessage = "Connected, but API key provisioning requires the AB01 channel."
        }
    }

    private func record(_ peripheral: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        let advertisedName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
        let serviceUUIDs = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []
        let serviceStrings = serviceUUIDs.map(\.uuidString)
        let name = advertisedName ?? peripheral.name ?? "Unknown Device"
        let serviceMatch = serviceUUIDs.contains { $0.matches(Self.provisioningServiceUUID) }
        let isLikelyProvisioningDevice = serviceMatch || Self.provisioningDeviceNameHints.contains { name.localizedCaseInsensitiveContains($0) }

        guard name != "Unknown Device" || serviceMatch else {
            return
        }

        peripheralsByID[peripheral.identifier] = peripheral

        let device = DiscoveredBLEDevice(
            id: peripheral.identifier,
            name: name,
            rssi: rssi.intValue,
            advertisedServices: serviceStrings,
            isLikelyProvisioningDevice: isLikelyProvisioningDevice,
            peripheral: peripheral
        )

        if let index = devices.firstIndex(where: { $0.id == device.id }) {
            devices[index] = device
        } else {
            devices.append(device)
        }

        devices.sort { lhs, rhs in
            if lhs.isLikelyProvisioningDevice != rhs.isLikelyProvisioningDevice {
                return lhs.isLikelyProvisioningDevice && !rhs.isLikelyProvisioningDevice
            }

            if lhs.rssi != rhs.rssi {
                return lhs.rssi > rhs.rssi
            }

            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
    }

    private func inspect(_ characteristic: CBCharacteristic, in service: CBService) {
        guard characteristic.isWriteable else {
            return
        }

        if characteristic.uuid.matches(Self.combinedCredentialCharacteristicUUID) {
            combinedCredentialCharacteristic = characteristic
        } else if characteristic.uuid.matches(Self.ssidCharacteristicUUID) {
            ssidCharacteristic = characteristic
        } else if characteristic.uuid.matches(Self.passwordCharacteristicUUID) {
            passwordCharacteristic = characteristic
        } else if characteristic.uuid.matches(Self.commandCharacteristicUUID) {
            commandCharacteristic = characteristic
        }

        updateReadyState()
    }

    private func queueWrite(_ string: String, to characteristic: CBCharacteristic, on peripheral: CBPeripheral) -> Bool {
        guard let data = string.data(using: .utf8) else {
            return false
        }

        return queueWrite(data, to: characteristic, on: peripheral)
    }

    private func queueWrite(_ data: Data, to characteristic: CBCharacteristic, on peripheral: CBPeripheral) -> Bool {
        guard let writeType = characteristic.preferredWriteType else {
            return false
        }

        let maxLength = max(20, peripheral.maximumWriteValueLength(for: writeType))
        writeQueue.append(
            WriteRequest(
                characteristic: characteristic,
                chunks: data.chunks(maxLength: maxLength),
                type: writeType
            )
        )

        return true
    }

    private func processNextWrite() {
        guard activeWrite == nil else {
            writeNextChunk()
            return
        }

        guard !writeQueue.isEmpty else {
            updateReadyState()
            statusMessage = sentCompletionMessage

            let completion = writeCompletion
            writeCompletion = nil
            completion?()
            return
        }

        activeWrite = writeQueue.removeFirst()
        writeNextChunk()
    }

    private func writeNextChunk() {
        guard let peripheral = connectedPeripheral, var activeWrite else {
            return
        }

        guard !activeWrite.chunks.isEmpty else {
            self.activeWrite = nil
            processNextWrite()
            return
        }

        let chunk = activeWrite.chunks.removeFirst()
        self.activeWrite = activeWrite

        peripheral.writeValue(chunk, for: activeWrite.characteristic, type: activeWrite.type)

        if activeWrite.type == .withoutResponse {
            DispatchQueue.main.async { [weak self] in
                self?.writeNextChunk()
            }
        }
    }

    private static let provisioningDeviceNameHints = [
        "arduino",
        "nano",
        "esp32",
        "esp-32",
        "firefly",
        "fire fly"
    ]

    private func disconnectFromProvisioningDevice(_ peripheral: CBPeripheral, message: String) {
        if connectedPeripheral?.identifier == peripheral.identifier {
            pendingDisconnectStatusMessage = message
            selectedDeviceID = nil
            connectedPeripheral = nil
            resetProvisioningCharacteristics()
            centralManager.cancelPeripheralConnection(peripheral)
        }

        statusMessage = message
    }
}

extension ProvisioningBLEManager: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            isBluetoothReady = true
            bluetoothStateMessage = "Bluetooth ready."
            statusMessage = "Scan for an ESP32 device."
        case .poweredOff:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth is off."
            statusMessage = "Turn on Bluetooth."
        case .unauthorized:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth permission is required."
            statusMessage = "Bluetooth permission is required."
        case .unsupported:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth provisioning requires a physical iPhone."
            statusMessage = "Bluetooth provisioning requires a physical iPhone."
        case .resetting:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth is resetting."
            statusMessage = "Bluetooth is resetting."
        case .unknown:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth state is unknown."
            statusMessage = "Bluetooth is starting."
        @unknown default:
            isBluetoothReady = false
            bluetoothStateMessage = "Bluetooth is unavailable."
            statusMessage = "Bluetooth is unavailable."
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        record(peripheral, advertisementData: advertisementData, rssi: RSSI)
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        connectedPeripheral = peripheral
        statusMessage = "Connected to \(peripheral.displayName)."
        peripheral.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        if selectedDeviceID == peripheral.identifier {
            selectedDeviceID = nil
            connectedPeripheral = nil
            resetProvisioningCharacteristics()
        }

        statusMessage = error?.localizedDescription ?? "Could not connect."
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        let disconnectMessage = pendingDisconnectStatusMessage ?? error?.localizedDescription ?? "Disconnected."
        pendingDisconnectStatusMessage = nil

        if selectedDeviceID == peripheral.identifier {
            selectedDeviceID = nil
            connectedPeripheral = nil
            resetProvisioningCharacteristics()
        }

        statusMessage = disconnectMessage
    }
}

extension ProvisioningBLEManager: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error {
            disconnectFromProvisioningDevice(
                peripheral,
                message: "Service discovery failed: \(error.localizedDescription)"
            )
            return
        }

        guard let services = peripheral.services, !services.isEmpty else {
            disconnectFromProvisioningDevice(
                peripheral,
                message: "Connected, but no BLE services were found."
            )
            return
        }

        pendingServiceDiscoveries = Set(services.map { $0.uuid.uuidString })
        for service in services {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error {
            finishServiceDiscovery(
                service,
                on: peripheral,
                failureMessage: "Characteristic discovery failed: \(error.localizedDescription)"
            )
            return
        }

        service.characteristics?.forEach { characteristic in
            inspect(characteristic, in: service)
        }

        finishServiceDiscovery(service, on: peripheral)
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error {
            writeQueue.removeAll()
            activeWrite = nil
            writeCompletion = nil
            updateReadyState()
            statusMessage = "Send failed: \(error.localizedDescription)"
            return
        }

        writeNextChunk()
    }

    private func finishServiceDiscovery(
        _ service: CBService,
        on peripheral: CBPeripheral,
        failureMessage: String? = nil
    ) {
        pendingServiceDiscoveries.remove(service.uuid.uuidString)

        guard pendingServiceDiscoveries.isEmpty else {
            if let failureMessage {
                statusMessage = failureMessage
            }
            return
        }

        guard !canSendCredentials else {
            return
        }

        let message = failureMessage ?? {
            if ssidCharacteristic != nil && passwordCharacteristic != nil {
                return "Connected, but API key provisioning requires the AB01 channel."
            }

            return "Connected, but no writable credential channel was found."
        }()

        disconnectFromProvisioningDevice(peripheral, message: message)
    }
}

private struct ProvisioningPayload: Encodable {
    let ssid: String
    let password: String
    let apiKey: String

    private enum CodingKeys: String, CodingKey {
        case ssid
        case password
        case apiKey = "api_key"
    }
}

enum ProvisioningCredentialValidator {
    static let maxSSIDBytes = 31
    static let maxPasswordBytes = 63
    static let maxAPIKeyBytes = 191
    static let maxPayloadBytes = 383

    static func validationMessage(ssid: String, password: String, apiKey: String) -> String? {
        let trimmedSSID = ssid.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedAPIKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedSSID.isEmpty else {
            return "SSID is required."
        }

        guard !trimmedAPIKey.isEmpty else {
            return "API key is required."
        }

        return limitMessage(ssid: trimmedSSID, password: password, apiKey: trimmedAPIKey)
    }

    static func limitMessage(ssid: String, password: String, apiKey: String) -> String? {
        if let message = byteLimitMessage("SSID", value: ssid, maxBytes: maxSSIDBytes) {
            return message
        }

        if let message = byteLimitMessage("Password", value: password, maxBytes: maxPasswordBytes) {
            return message
        }

        if let message = byteLimitMessage("API key", value: apiKey, maxBytes: maxAPIKeyBytes) {
            return message
        }

        do {
            _ = try payloadData(ssid: ssid, password: password, apiKey: apiKey)
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    static func payloadData(ssid: String, password: String, apiKey: String) throws -> Data {
        let payload = ProvisioningPayload(
            ssid: ssid,
            password: password,
            apiKey: apiKey
        )

        var payloadData = try JSONEncoder().encode(payload)
        payloadData.append(0x0A)

        guard payloadData.count <= maxPayloadBytes else {
            throw ProvisioningCredentialValidationError.payloadTooLarge(
                maxBytes: maxPayloadBytes,
                actualBytes: payloadData.count
            )
        }

        return payloadData
    }

    private static func byteLimitMessage(_ name: String, value: String, maxBytes: Int) -> String? {
        let byteCount = value.utf8.count
        guard byteCount > maxBytes else {
            return nil
        }

        return "\(name) must be \(maxBytes) UTF-8 bytes or fewer. Current value is \(byteCount) bytes."
    }
}

enum ProvisioningCredentialValidationError: LocalizedError {
    case payloadTooLarge(maxBytes: Int, actualBytes: Int)

    var errorDescription: String? {
        switch self {
        case .payloadTooLarge(let maxBytes, let actualBytes):
            return "Credential payload must be \(maxBytes) bytes or fewer after JSON encoding. Current payload is \(actualBytes) bytes."
        }
    }
}

private struct WriteRequest {
    let characteristic: CBCharacteristic
    var chunks: [Data]
    let type: CBCharacteristicWriteType
}

private extension CBPeripheral {
    var displayName: String {
        name ?? "ESP32"
    }
}

private extension CBCharacteristic {
    var isWriteable: Bool {
        properties.contains(.write) || properties.contains(.writeWithoutResponse)
    }

    var preferredWriteType: CBCharacteristicWriteType? {
        if properties.contains(.write) {
            return .withResponse
        }

        if properties.contains(.writeWithoutResponse) {
            return .withoutResponse
        }

        return nil
    }
}

private extension CBUUID {
    func matches(_ other: CBUUID) -> Bool {
        uuidString.caseInsensitiveCompare(other.uuidString) == .orderedSame
    }
}

private extension Data {
    func chunks(maxLength: Int) -> [Data] {
        guard !isEmpty else {
            return [Data()]
        }

        guard count > maxLength else {
            return [self]
        }

        var chunks: [Data] = []
        var offset = 0

        while offset < count {
            let end = Swift.min(offset + maxLength, count)
            chunks.append(subdata(in: offset..<end))
            offset = end
        }

        return chunks
    }
}
