//
//  CredentialStore.swift
//  FireFLY
//
//  Created by MacBook Pro on 5/10/26.
//

import Foundation
import Security

nonisolated struct WiFiCredentials: Codable, Equatable {
    let ssid: String
    let password: String
    let apiKey: String

    init(ssid: String, password: String, apiKey: String = "") {
        self.ssid = ssid
        self.password = password
        self.apiKey = apiKey
    }

    private enum CodingKeys: String, CodingKey {
        case ssid
        case password
        case apiKey = "api_key"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ssid = try container.decode(String.self, forKey: .ssid)
        password = try container.decode(String.self, forKey: .password)
        apiKey = try container.decodeIfPresent(String.self, forKey: .apiKey) ?? ""
    }
}

final class CredentialStore {
    private let service = "edu.ucsc.cse123.FireFLY.wifi"
    private let account = "default-network"

    func save(_ credentials: WiFiCredentials) throws {
        let data = try JSONEncoder().encode(credentials)
        SecItemDelete(baseQuery as CFDictionary)

        var query = baseQuery
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw CredentialStoreError.keychain(status)
        }
    }

    func load() throws -> WiFiCredentials? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        switch status {
        case errSecSuccess:
            guard let data = item as? Data else {
                throw CredentialStoreError.invalidData
            }

            return try JSONDecoder().decode(WiFiCredentials.self, from: data)
        case errSecItemNotFound:
            return nil
        default:
            throw CredentialStoreError.keychain(status)
        }
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}

enum CredentialStoreError: LocalizedError {
    case invalidData
    case keychain(OSStatus)

    var errorDescription: String? {
        switch self {
        case .invalidData:
            return "Saved credentials are not readable."
        case .keychain(let status):
            return "Keychain error \(status)."
        }
    }
}
