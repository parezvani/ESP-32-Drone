//
//  FireFLYAuthStore.swift
//  FireFLY
//

import Combine
import Foundation
import Supabase

struct FireFLYProfile: Decodable, Equatable {
    let id: UUID
    let fullName: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case fullName = "full_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

@MainActor
final class FireFLYAuthStore: ObservableObject {
    enum Phase: Equatable {
        case restoring
        case signedOut
        case signedIn
    }

    @Published private(set) var phase: Phase = .restoring
    @Published private(set) var session: Session?
    @Published private(set) var profile: FireFLYProfile?
    @Published private(set) var isWorking = false
    @Published var message = ""

    private var authObservationTask: Task<Void, Never>?

    deinit {
        authObservationTask?.cancel()
    }

    var displayName: String {
        if let fullName = profile?.fullName?.trimmingCharacters(in: .whitespacesAndNewlines),
           !fullName.isEmpty {
            return fullName
        }

        return session?.user.email ?? "FireFLY Operator"
    }

    var accountEmail: String {
        session?.user.email ?? "Signed in with Supabase"
    }

    func start() {
        guard authObservationTask == nil else {
            return
        }

        authObservationTask = Task { [weak self] in
            for await (event, session) in FireFLYSupabase.client.auth.authStateChanges {
                await self?.handleAuthEvent(event, session: session)
            }
        }
    }

    func signIn(email: String, password: String) async {
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedEmail.isEmpty, !password.isEmpty else {
            message = "Email and password are required."
            return
        }

        isWorking = true
        message = ""
        defer { isWorking = false }

        do {
            try await FireFLYSupabase.client.auth.signIn(
                email: trimmedEmail,
                password: password
            )
        } catch {
            message = error.localizedDescription
        }
    }

    func signUp(fullName: String, email: String, password: String) async {
        let trimmedName = fullName.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedName.isEmpty, !trimmedEmail.isEmpty, !password.isEmpty else {
            message = "Name, email, and password are required."
            return
        }

        isWorking = true
        message = ""
        defer { isWorking = false }

        do {
            let response = try await FireFLYSupabase.client.auth.signUp(
                email: trimmedEmail,
                password: password,
                data: [
                    "full_name": .string(trimmedName)
                ]
            )

            if response.session == nil {
                phase = .signedOut
                message = "Account created. Confirm your email, then sign in."
            }
        } catch {
            message = error.localizedDescription
        }
    }

    func signOut() async {
        isWorking = true
        message = ""
        defer { isWorking = false }

        do {
            try await FireFLYSupabase.client.auth.signOut()
        } catch {
            message = error.localizedDescription
        }
    }

    func loadCurrentProfile() async {
        guard let userID = session?.user.id else {
            profile = nil
            return
        }

        do {
            let profile: FireFLYProfile = try await FireFLYSupabase.client
                .from("profiles")
                .select("id, full_name, created_at, updated_at")
                .eq("id", value: userID)
                .single()
                .execute()
                .value

            self.profile = profile
        } catch {
            profile = nil
        }
    }

    private func handleAuthEvent(_ event: AuthChangeEvent, session: Session?) async {
        switch event {
        case .initialSession:
            self.session = session

            if let session, session.isExpired {
                profile = nil
                phase = .restoring
                return
            }

            await enterAuthenticatedState(using: session)
        case .signedIn, .tokenRefreshed, .userUpdated:
            await enterAuthenticatedState(using: session)
        case .signedOut:
            self.session = nil
            profile = nil
            phase = .signedOut
        default:
            break
        }
    }

    private func enterAuthenticatedState(using session: Session?) async {
        self.session = session

        if session == nil {
            profile = nil
            phase = .signedOut
        } else {
            phase = .signedIn
            await loadCurrentProfile()
        }
    }
}
