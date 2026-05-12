//
//  CredentialStore.swift
//  FireFLY
//
//  Created by MacBook Pro on 5/10/26.
//

import Foundation
import Security

struct WiFiCredentials: Codable, Equatable {
    let ssid: String
    let password: String
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
