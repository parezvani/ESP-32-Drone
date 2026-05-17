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

}
