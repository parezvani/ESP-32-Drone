//
//  FireFLYApp.swift
//  FireFLY
//
//  Created by MacBook Pro on 5/10/26.
//

import SwiftUI

@main
struct FireFLYApp: App {
    @StateObject private var authStore = FireFLYAuthStore()

    var body: some Scene {
        WindowGroup {
            AppRootView()
                .environmentObject(authStore)
        }
    }
}
