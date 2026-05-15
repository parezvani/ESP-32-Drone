//
//  AppRootView.swift
//  FireFLY
//

import Auth
import Supabase
import SwiftUI

struct AppRootView: View {
    @EnvironmentObject private var authStore: FireFLYAuthStore
    private let startsAuthObservation: Bool

    init(startsAuthObservation: Bool = true) {
        self.startsAuthObservation = startsAuthObservation
    }

    var body: some View {
        Group {
            switch authStore.phase {
            case .restoring:
                AuthRestoreView()
            case .signedOut:
                FireFLYAuthView()
            case .signedIn:
                ContentView()
            }
        }
        .task {
            if startsAuthObservation {
                authStore.start()
            }
        }
        .onOpenURL { url in
            FireFLYSupabase.client.handle(url)
        }
    }
}

private struct AuthRestoreView: View {
    var body: some View {
        ZStack {
            FireFLYAuthBackground()

            VStack(spacing: 16) {
                ProgressView()
                    .controlSize(.large)

                Text("Restoring your FireFLY session")
                    .font(.headline.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            .padding(28)
            .glassEffect(
                .regular.tint(Color.white.opacity(0.16)),
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
        }
    }
}

private struct FireFLYAuthView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case signIn = "Sign In"
        case signUp = "Create Account"

        var id: String { rawValue }
    }

    @EnvironmentObject private var authStore: FireFLYAuthStore

    @State private var mode: Mode = .signIn
    @State private var fullName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var localMessage = ""

    var body: some View {
        ScrollView {
            GlassEffectContainer(spacing: 18) {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("FireFLY")
                            .font(.system(size: 38, weight: .bold, design: .rounded))

                        Text(mode == .signIn ? "Sign in to continue" : "Create your FireFLY account")
                            .font(.headline.weight(.medium))
                            .foregroundStyle(.secondary)
                    }

                    Picker("Authentication mode", selection: $mode) {
                        ForEach(Mode.allCases) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)

                    if mode == .signUp {
                        TextField("Full name", text: $fullName)
                            .textContentType(.name)
                            .fieldChrome()
                    }

                    TextField("Email", text: $email)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .fieldChrome()

                    SecureField("Password", text: $password)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textContentType(mode == .signIn ? .password : .newPassword)
                        .fieldChrome()

                    if mode == .signUp {
                        SecureField("Confirm password", text: $confirmPassword)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .textContentType(.newPassword)
                            .fieldChrome()
                    }

                    Button {
                        submit()
                    } label: {
                        Label(
                            mode == .signIn ? "Sign In" : "Create Account",
                            systemImage: mode == .signIn ? "arrow.right.circle.fill" : "person.crop.circle.badge.plus"
                        )
                        .font(.title3.weight(.semibold))
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.glassProminent)
                    .controlSize(.large)
                    .tint(.blue)
                    .disabled(authStore.isWorking)

                    OAuthDivider()

                    VStack(spacing: 12) {
                        OAuthProviderButton(
                            title: "Continue with Google",
                            imageName: "GoogleLogo"
                        ) {
                            Task {
                                await authStore.signInWithOAuth(provider: .google)
                            }
                        }

                        OAuthProviderButton(
                            title: "Continue with GitHub",
                            imageName: "GitHubLogo"
                        ) {
                            Task {
                                await authStore.signInWithOAuth(provider: .github)
                            }
                        }
                    }
                    .disabled(authStore.isWorking)

                    if !statusText.isEmpty {
                        Text(statusText)
                            .font(.body.weight(.medium))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 28)
                .frame(maxWidth: 620, alignment: .leading)
            }
            .padding(.top, 48)
            .padding(.bottom, 32)
        }
        .background {
            FireFLYAuthBackground()
        }
        .onChange(of: mode) { _, _ in
            localMessage = ""
        }
    }

    private var statusText: String {
        localMessage.isEmpty ? authStore.message : localMessage
    }

    private func submit() {
        localMessage = ""

        switch mode {
        case .signIn:
            Task {
                await authStore.signIn(email: email, password: password)
            }
        case .signUp:
            guard password.count >= 6 else {
                localMessage = "Password must be at least 6 characters."
                return
            }

            guard password == confirmPassword else {
                localMessage = "Passwords do not match."
                return
            }

            Task {
                await authStore.signUp(
                    fullName: fullName,
                    email: email,
                    password: password
                )
            }
        }
    }
}

private struct OAuthDivider: View {
    var body: some View {
        HStack(spacing: 12) {
            Rectangle()
                .fill(Color.secondary.opacity(0.45))
                .frame(height: 1)

            Text("or")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Rectangle()
                .fill(Color.secondary.opacity(0.45))
                .frame(height: 1)
        }
    }
}

private struct OAuthProviderButton: View {
    let title: String
    let imageName: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(.white.opacity(0.96))

                    Image(imageName)
                        .renderingMode(.original)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 20, height: 20)
                }
                .frame(width: 28, height: 28)

                Text(title)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.white)
            }
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.glassProminent)
        .controlSize(.large)
        .tint(.blue)
    }
}

private struct FireFLYAuthBackground: View {
    var body: some View {
        LinearGradient(
            colors: [
                Color(uiColor: .systemBackground),
                Color.blue.opacity(0.08),
                Color.green.opacity(0.06),
                Color(uiColor: .systemBackground)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }
}

private extension View {
    func fieldChrome() -> some View {
        self
            .font(.title2)
            .padding(.horizontal, 16)
            .frame(minHeight: 62)
            .glassEffect(
                .regular.tint(Color.white.opacity(0.18)).interactive(),
                in: RoundedRectangle(cornerRadius: 18, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(Color.white.opacity(0.35), lineWidth: 1)
            )
    }
}

#if DEBUG
#Preview("Signed Out") {
    AppRootView(startsAuthObservation: false)
        .environmentObject(FireFLYAuthStore.preview(phase: .signedOut))
}

#Preview("Restoring") {
    AppRootView(startsAuthObservation: false)
        .environmentObject(FireFLYAuthStore.preview(phase: .restoring))
}

#Preview("Signed In") {
    AppRootView(startsAuthObservation: false)
        .environmentObject(FireFLYAuthStore.preview(phase: .signedIn))
}
#endif
