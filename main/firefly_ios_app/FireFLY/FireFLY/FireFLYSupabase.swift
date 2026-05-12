//
//  FireFLYSupabase.swift
//  FireFLY
//

import Foundation
import Supabase

enum FireFLYSupabase {
    static let client = SupabaseClient(
        supabaseURL: URL(string: "https://qgvlhplbeisltvmasqdd.supabase.co")!,
        supabaseKey: "sb_publishable_o3AjV-xwWYaM5ev9MslFvA_mGoz5TRT",
        options: SupabaseClientOptions(
            auth: .init(
                emitLocalSessionAsInitialSession: true
            )
        )
    )
}
