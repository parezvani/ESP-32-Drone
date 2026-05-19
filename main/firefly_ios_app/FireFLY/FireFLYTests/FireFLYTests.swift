//
//  FireFLYTests.swift
//  FireFLYTests
//
//  Created by MacBook Pro on 5/10/26.
//

import Foundation
import Testing
@testable import FireFLY

struct FireFLYTests {

    @Test func oldSavedCredentialsDecodeWithEmptyAPIKey() throws {
        let data = Data(#"{"ssid":"Lab WiFi","password":"secret"}"#.utf8)

        let credentials = try JSONDecoder().decode(WiFiCredentials.self, from: data)

        #expect(credentials.ssid == "Lab WiFi")
        #expect(credentials.password == "secret")
        #expect(credentials.apiKey == "")
    }

    @Test func credentialsEncodeAPIKeyUsingBLEFieldName() throws {
        let credentials = WiFiCredentials(
            ssid: "Lab WiFi",
            password: "secret",
            apiKey: "firefly-key"
        )

        let data = try JSONEncoder().encode(credentials)
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: String]
        )

        #expect(object["ssid"] == "Lab WiFi")
        #expect(object["password"] == "secret")
        #expect(object["api_key"] == "firefly-key")
        #expect(object["apiKey"] == nil)
    }

    @Test func provisioningPayloadUsesBLEFieldNameAndTrailingNewline() throws {
        let data = try ProvisioningCredentialValidator.payloadData(
            ssid: "Lab WiFi",
            password: "secret",
            apiKey: "firefly-key"
        )

        #expect(data.last == 0x0A)

        let object = try #require(
            JSONSerialization.jsonObject(with: data.dropLast()) as? [String: String]
        )

        #expect(object["ssid"] == "Lab WiFi")
        #expect(object["password"] == "secret")
        #expect(object["api_key"] == "firefly-key")
        #expect(object["apiKey"] == nil)
    }

    @Test func provisioningValidatorAllowsFirmwareMaximumFieldSizes() throws {
        let ssid = String(repeating: "s", count: ProvisioningCredentialValidator.maxSSIDBytes)
        let password = String(repeating: "p", count: ProvisioningCredentialValidator.maxPasswordBytes)
        let apiKey = String(repeating: "k", count: ProvisioningCredentialValidator.maxAPIKeyBytes)

        let message = ProvisioningCredentialValidator.validationMessage(
            ssid: ssid,
            password: password,
            apiKey: apiKey
        )
        let payload = try ProvisioningCredentialValidator.payloadData(
            ssid: ssid,
            password: password,
            apiKey: apiKey
        )

        #expect(message == nil)
        #expect(payload.count <= ProvisioningCredentialValidator.maxPayloadBytes)
    }

    @Test func provisioningValidatorRejectsOversizedFields() {
        let ssid = String(repeating: "s", count: ProvisioningCredentialValidator.maxSSIDBytes + 1)
        let password = String(repeating: "p", count: ProvisioningCredentialValidator.maxPasswordBytes + 1)
        let apiKey = String(repeating: "k", count: ProvisioningCredentialValidator.maxAPIKeyBytes + 1)

        #expect(
            ProvisioningCredentialValidator.validationMessage(
                ssid: ssid,
                password: "",
                apiKey: "key"
            ) == "SSID must be 31 UTF-8 bytes or fewer. Current value is 32 bytes."
        )
        #expect(
            ProvisioningCredentialValidator.validationMessage(
                ssid: "Lab WiFi",
                password: password,
                apiKey: "key"
            ) == "Password must be 63 UTF-8 bytes or fewer. Current value is 64 bytes."
        )
        #expect(
            ProvisioningCredentialValidator.validationMessage(
                ssid: "Lab WiFi",
                password: "",
                apiKey: apiKey
            ) == "API key must be 191 UTF-8 bytes or fewer. Current value is 192 bytes."
        )
    }

    @Test func provisioningValidatorRejectsMissingRequiredFields() {
        #expect(
            ProvisioningCredentialValidator.validationMessage(
                ssid: " ",
                password: "",
                apiKey: "key"
            ) == "SSID is required."
        )
        #expect(
            ProvisioningCredentialValidator.validationMessage(
                ssid: "Lab WiFi",
                password: "",
                apiKey: " "
            ) == "API key is required."
        )
    }

}
