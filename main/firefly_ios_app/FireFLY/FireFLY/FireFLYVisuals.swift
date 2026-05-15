//
//  FireFLYVisuals.swift
//  FireFLY
//

import SwiftUI
import UIKit

struct FireFLYBackground: View {
    var body: some View {
        LinearGradient(
            colors: [
                Color(uiColor: .systemBackground),
                Color.cyan.opacity(0.10),
                Color.green.opacity(0.06),
                Color.orange.opacity(0.07),
                Color(uiColor: .systemBackground)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .overlay {
            LinearGradient(
                colors: [
                    Color.white.opacity(0.20),
                    Color.clear,
                    Color.black.opacity(0.04)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .blendMode(.softLight)
        }
        .ignoresSafeArea()
    }
}

struct FireFLYSectionHeader: View {
    let title: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.headline.weight(.semibold))
                .foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .glassEffect(
                    .regular.tint(tint.opacity(0.12)),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                )

            Text(title)
                .font(.title2.weight(.bold))
                .foregroundStyle(.primary)
        }
    }
}

struct FireFLYInlineStatus: View {
    let message: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
                .frame(width: 18, height: 18)

            Text(message)
                .font(.body.weight(.medium))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct FireFLYStatusNote: View {
    let message: String
    let systemImage: String
    let tint: Color

    init(message: String, systemImage: String = "info.circle.fill", tint: Color = .blue) {
        self.message = message
        self.systemImage = systemImage
        self.tint = tint
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
                .frame(width: 18, height: 18)

            Text(message)
                .font(.body.weight(.medium))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fireFLYGlassPanel(cornerRadius: 14, tint: tint.opacity(0.08))
    }
}

private struct FireFLYGlassPanelModifier: ViewModifier {
    let cornerRadius: CGFloat
    let tint: Color
    let isInteractive: Bool

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        content
            .glassEffect(
                isInteractive ? .regular.tint(tint).interactive() : .regular.tint(tint),
                in: shape
            )
            .overlay(
                shape.stroke(Color.white.opacity(0.30), lineWidth: 1)
            )
    }
}

private struct FireFLYFieldChromeModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(.title3)
            .padding(.horizontal, 16)
            .frame(minHeight: 58)
            .fireFLYGlassPanel(
                cornerRadius: 16,
                tint: Color.white.opacity(0.16),
                isInteractive: true
            )
    }
}

extension View {
    func fireFLYGlassPanel(
        cornerRadius: CGFloat = 18,
        tint: Color = Color.white.opacity(0.16),
        isInteractive: Bool = false
    ) -> some View {
        modifier(
            FireFLYGlassPanelModifier(
                cornerRadius: cornerRadius,
                tint: tint,
                isInteractive: isInteractive
            )
        )
    }

    func fireFLYFieldChrome() -> some View {
        modifier(FireFLYFieldChromeModifier())
    }
}
