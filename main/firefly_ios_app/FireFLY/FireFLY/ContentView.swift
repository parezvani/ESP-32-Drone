//
//  ContentView.swift
//  FireFLY
//
//  Created by MacBook Pro on 5/10/26.
//

import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject private var authStore: FireFLYAuthStore
    @StateObject private var bluetooth = ProvisioningBLEManager()

    @State private var ssid = ""
    @State private var password = ""
    @State private var restoreMessage = ""
    @State private var isPasswordVisible = false

    private let credentialStore = CredentialStore()

    var body: some View {
        ScrollView {
            GlassEffectContainer(spacing: 18) {
                VStack(alignment: .leading, spacing: 28) {
                    appHeader
                    credentialsSection
                    esp32Section
                    provisionSection
                }
                .padding(.horizontal, 22)
                .padding(.top, 24)
                .padding(.bottom, 32)
                .frame(maxWidth: 620, alignment: .leading)
            }
        }
        .scrollIndicators(.hidden)
        .frame(maxWidth: .infinity, alignment: .top)
        .background {
            FireFLYBackground()
        }
    }

    private var appHeader: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "person.crop.circle.fill")
                .font(.system(size: 24))
                .foregroundStyle(.blue)
                .frame(width: 32, height: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(authStore.displayName)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.84)

                Text(authStore.accountEmail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer(minLength: 8)

            Button {
                Task {
                    await authStore.signOut()
                }
            } label: {
                ViewThatFits(in: .horizontal) {
                    Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: true, vertical: false)

                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .font(.subheadline.weight(.semibold))
                        .frame(width: 16, height: 16)
                }
            }
            .buttonStyle(.glass)
            .controlSize(.regular)
            .tint(.orange)
            .disabled(authStore.isWorking)
            .accessibilityLabel("Sign Out")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(minHeight: 60)
        .fireFLYGlassPanel(cornerRadius: 16, isInteractive: true)
    }

    private var credentialsSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            FireFLYSectionHeader(title: "WiFi Credentials", systemImage: "wifi", tint: .blue)

            TextField("Network name", text: $ssid)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.username)
                .submitLabel(.next)
                .fireFLYFieldChrome()

            HStack(spacing: 10) {
                Group {
                    if isPasswordVisible {
                        TextField("Password", text: $password)
                    } else {
                        SecureField("Password", text: $password)
                    }
                }
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.password)
                .privacySensitive()

                Button {
                    isPasswordVisible.toggle()
                } label: {
                    Image(systemName: isPasswordVisible ? "eye.slash" : "eye")
                        .font(.body.weight(.semibold))
                        .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .accessibilityLabel(isPasswordVisible ? "Hide password" : "Show password")
            }
            .fireFLYFieldChrome()

            Button {
                restoreSavedCredentials()
            } label: {
                Label("Restore Saved Credentials", systemImage: "key")
                    .font(.title3.weight(.medium))
            }
            .buttonStyle(.glass)
            .controlSize(.large)
            .tint(.blue)

            if !restoreMessage.isEmpty {
                FireFLYInlineStatus(
                    message: restoreMessage,
                    systemImage: "key.fill",
                    tint: .blue
                )
            }
        }
    }

    private var esp32Section: some View {
        VStack(alignment: .leading, spacing: 14) {
            FireFLYSectionHeader(
                title: "ESP32",
                systemImage: "antenna.radiowaves.left.and.right",
                tint: .green
            )

            Button {
                bluetooth.isScanning ? bluetooth.stopScanning() : bluetooth.startScanning()
            } label: {
                Label(
                    bluetooth.isScanning ? "Stop Scan" : "Scan for ESP32",
                    systemImage: bluetooth.isScanning ? "stop.circle" : "antenna.radiowaves.left.and.right"
                )
                .font(.title3.weight(.medium))
            }
            .buttonStyle(.glass)
            .controlSize(.large)
            .tint(bluetooth.isScanning ? .orange : .green)
            .disabled(!bluetooth.isBluetoothReady)

            if !bluetooth.devices.isEmpty {
                VStack(spacing: 12) {
                    ForEach(bluetooth.devices) { device in
                        Button {
                            bluetooth.connect(to: device)
                        } label: {
                            DeviceRow(
                                device: device,
                                isSelected: bluetooth.selectedDeviceID == device.id
                            )
                        }
                        .buttonStyle(.glass)
                        .controlSize(.large)
                        .tint(device.isLikelyProvisioningDevice ? .green : .blue)
                        .disabled(bluetooth.selectedDeviceID == device.id)
                    }
                }
            }

            if bluetooth.devices.isEmpty {
                FireFLYInlineStatus(
                    message: bluetooth.bluetoothStateMessage,
                    systemImage: bluetooth.isBluetoothReady
                        ? "antenna.radiowaves.left.and.right"
                        : "exclamationmark.triangle.fill",
                    tint: bluetooth.isBluetoothReady ? .green : .blue
                )
            }
        }
    }

    private var provisionSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            FireFLYSectionHeader(title: "Provision", systemImage: "paperplane.fill", tint: .orange)

            Button {
                sendCredentials()
            } label: {
                Label("Send Credentials", systemImage: "paperplane.fill")
                    .font(.title3.weight(.semibold))
            }
            .buttonStyle(.glassProminent)
            .controlSize(.large)
            .tint(.orange)
            .disabled(!canSend)

            FireFLYInlineStatus(
                message: bluetooth.statusMessage,
                systemImage: canSend ? "checkmark.circle.fill" : "info.circle.fill",
                tint: canSend ? .green : .orange
            )
        }
    }

    private var canSend: Bool {
        bluetooth.canSendCredentials && !ssid.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func restoreSavedCredentials() {
        do {
            guard let credentials = try credentialStore.load() else {
                restoreMessage = "No saved credentials."
                return
            }

            ssid = credentials.ssid
            password = credentials.password
            restoreMessage = "Saved credentials restored."
        } catch {
            restoreMessage = "Could not restore saved credentials."
        }
    }

    private func sendCredentials() {
        let trimmedSSID = ssid.trimmingCharacters(in: .whitespacesAndNewlines)
        guard bluetooth.sendCredentials(ssid: trimmedSSID, password: password) else {
            return
        }

        do {
            try credentialStore.save(WiFiCredentials(ssid: trimmedSSID, password: password))
        } catch {
            restoreMessage = "Credentials sent, but not saved."
        }
    }
}

private struct DeviceRow: View {
    let device: DiscoveredBLEDevice
    let isSelected: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            Image(systemName: device.isLikelyProvisioningDevice ? "cpu.fill" : "cpu")
                .font(.title2.weight(.semibold))
                .foregroundStyle(device.isLikelyProvisioningDevice ? .green : .blue)
                .frame(width: 34, height: 34)
                .glassEffect(
                    .regular.tint((device.isLikelyProvisioningDevice ? Color.green : Color.blue).opacity(0.10)),
                    in: RoundedRectangle(cornerRadius: 11, style: .continuous)
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(device.name)
                    .font(.title2)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)

                Text(device.detailText)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer(minLength: 12)

            VStack(alignment: .trailing, spacing: 8) {
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.green)
                }

                Text(device.signalText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(device.rssi > -70 ? .green : .secondary)
            }
        }
        .contentShape(Rectangle())
    }
}

#if DEBUG
#Preview("Provisioning") {
    ContentView()
        .environmentObject(FireFLYAuthStore.preview(phase: .signedIn))
}
#endif
