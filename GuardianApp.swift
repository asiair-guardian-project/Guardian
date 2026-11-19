import SwiftUI
import Foundation
import Darwin

struct GuardianReply {
    let raw: [String: Any]
    var ok: Bool { raw["ok"] as? Bool == true }
    var code: String { raw["code"] as? String ?? "UNKNOWN" }
    var message: String { raw["message"] as? String ?? code }
    func bool(_ key: String) -> Bool { raw[key] as? Bool == true }
    func string(_ key: String) -> String { raw[key] as? String ?? "" }
}

// Where the operator socket lives. A rehearsal sets GUARDIAN_V1_SOCKET to the socket of a SIMULATED rig
// (see guardian_v1_sim_night.py); normally this is the live monitor's socket.
let guardianRehearsalSocket: String? = {
    if let value = ProcessInfo.processInfo.environment["GUARDIAN_V1_SOCKET"], value.hasPrefix("/") { return value }
    return nil
}()
let guardianSocketPath: String = guardianRehearsalSocket ?? (NSHomeDirectory() + "/Library/Application Support/GuardianV1/operator.sock")

enum IPCError: LocalizedError {
    case unavailable, invalidResponse, oversized, system(String)
    var errorDescription: String? {
        switch self {
        case .unavailable: return "Guardian operator socket is unavailable"
        case .invalidResponse: return "Invalid Guardian response"
        case .oversized: return "Guardian response exceeded size limit"
        case .system(let message): return message
        }
    }
}

// Only communicates with the Guardian-owned, private local Unix socket.
// Never reads or modifies Guardian's recovery store or controls hardware.
func sendGuardian(_ request: [String: Any], at path: String) throws -> GuardianReply {
    var info = stat()
    guard lstat(path, &info) == 0, (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFSOCK) else {
        throw IPCError.unavailable
    }
    guard info.st_uid == getuid(), (info.st_mode & 0o077) == 0 else {
        throw IPCError.system("Operator socket has unexpected ownership or permissions")
    }
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw IPCError.system("Unable to open local socket") }
    defer { close(fd) }
    var timeout = timeval(tv_sec: 2, tv_usec: 0)
    _ = withUnsafePointer(to: &timeout) {
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, $0, socklen_t(MemoryLayout<timeval>.size))
    }
    _ = withUnsafePointer(to: &timeout) {
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, $0, socklen_t(MemoryLayout<timeval>.size))
    }
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let bytes = Array(path.utf8)
    let capacity = MemoryLayout.size(ofValue: address.sun_path)
    guard bytes.count < capacity else { throw IPCError.system("Socket path too long") }
    withUnsafeMutableBytes(of: &address.sun_path) { buffer in
        for (index, byte) in bytes.enumerated() { buffer[index] = byte }
        buffer[bytes.count] = 0
    }
    let connected = withUnsafePointer(to: &address) { ptr in
        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard connected == 0 else { throw IPCError.system("Could not connect to Guardian operator service") }
    var payload = try JSONSerialization.data(withJSONObject: request)
    payload.append(0x0A)
    try payload.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { throw IPCError.invalidResponse }
        var sent = 0
        while sent < raw.count {
            let n = Darwin.send(fd, base.advanced(by: sent), raw.count - sent, 0)
            guard n > 0 else { throw IPCError.system("Operator request failed") }
            sent += n
        }
    }
    var data = Data()
    var buffer = [UInt8](repeating: 0, count: 2048)
    while data.count <= 16384 {
        let n = recv(fd, &buffer, buffer.count, 0)
        if n < 0 { throw IPCError.system("Guardian socket read failed (errno \(errno))") }
        if n == 0 { throw IPCError.system("Guardian closed connection before response") }
        data.append(contentsOf: buffer.prefix(n))
        if data.contains(0x0A) { break }
    }
    guard data.count <= 16384 else { throw IPCError.oversized }
    guard let end = data.firstIndex(of: 0x0A) else { throw IPCError.invalidResponse }
    let json = try JSONSerialization.jsonObject(with: data.prefix(upTo: end))
    guard let object = json as? [String: Any], object["ok"] is Bool else { throw IPCError.invalidResponse }
    return GuardianReply(raw: object)
}

@MainActor final class GuardianModel: ObservableObject {
    @Published var status: GuardianReply?
    @Published var connection = "Connecting…"
    @Published var busy = false
    @Published var notice: String?
    @Published var showSetup = false
    let socketPath = guardianSocketPath

    func refresh() async {
        do {
            let path = socketPath
            let result = try await Task.detached { try sendGuardian(["command": "STATUS"], at: path) }.value
            guard result.ok && result.code == "STATUS" else { throw IPCError.invalidResponse }
            status = result
            connection = "Connected"
        } catch {
            status = nil
            connection = "Unavailable: \(error.localizedDescription)"
        }
    }
    func command(_ payload: [String: Any]) async {
        busy = true
        defer { busy = false }
        do {
            let path = socketPath
            let response = try await Task.detached { try sendGuardian(payload, at: path) }.value
            notice = response.message
        } catch { notice = error.localizedDescription }
        await refresh()
    }
}

struct ContentView: View {
    @StateObject private var model = GuardianModel()
    @State private var confirmation: Confirmation?
    enum Confirmation: String, Identifiable { case arm, disarm, acknowledge, release
        var id: String { rawValue }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if guardianRehearsalSocket != nil {
                Text("REHEARSAL — simulated rig. This is NOT the live Guardian.")
                    .font(.headline).foregroundStyle(.white)
                    .frame(maxWidth: .infinity).padding(8)
                    .background(Color.purple)
            }
            HStack {
                Image(systemName: "shield.lefthalf.filled").font(.system(size: 34))
                VStack(alignment: .leading) {
                    Text("Guardian 1.0").font(.largeTitle.bold())
                    Text("Observatory Supervisor · Operator dashboard").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Setup") { model.showSetup = true }
                Button("Refresh") { Task { await model.refresh() } }
            }
            Divider()
            LabeledContent("Connection", value: model.connection)
            LabeledContent("Session", value: model.status?.string("session") ?? "Unknown")
            GroupBox("Equipment · live observations") {
                VStack(alignment: .leading, spacing: 8) {
                    if let equipment = model.status?.raw["equipment"] as? [String: Any] {
                        LabeledContent("Roof safety", value: equipment["roof"] as? String ?? "Unknown")
                        LabeledContent("Controller", value: equipment["controller"] as? String ?? "Unknown")
                        LabeledContent("Observed UTC", value: equipment["observed_at_utc"] as? String ?? "Unknown")
                    } else {
                        Text("No recent observation — status unavailable").foregroundStyle(.secondary)
                    }
                    LabeledContent("Power/data hub", value: "Not monitored by this interface")
                }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
            }
            LabeledContent("Hardware execution", value: model.status == nil ? "Unknown" : (model.status!.bool("hardware_execution_enabled") ? "ENABLED" : "DISABLED"))
            LabeledContent("ARM authorization", value: model.status == nil ? "Unknown" : (model.status!.bool("arm_available") ? "Available" : "Unavailable"))
            LabeledContent("ARM", value: model.status == nil ? "Unknown" : (model.status!.bool("armed") ? "ARMED" : "DISARMED"))
            LabeledContent("Recovery", value: model.status == nil ? "Unknown" : (model.status!.bool("arm_blocked") ? "ARM BLOCKED" : "No active block reported"))
            if let status = model.status {
                if !status.string("arm_unavailable_reason").isEmpty {
                    Text("ARM unavailable: \(status.string("arm_unavailable_reason"))").foregroundStyle(.orange)
                }
                if !status.string("recovery_reason").isEmpty {
                    Text("Reason: \(status.string("recovery_reason"))").foregroundStyle(.orange)
                }
                if status.bool("incident_active") {
                    Text("RECOVERY REQUIRED — incident \(status.bool("acknowledged") ? "acknowledged" : "awaiting acknowledgment")")
                        .font(.headline).foregroundStyle(.red)
                    if let unresolved = status.raw["unresolved_actions"] as? [String], !unresolved.isEmpty {
                        Text("Unresolved: \(unresolved.joined(separator: ", "))")
                    }
                    if status.bool("acknowledged") {
                        if status.bool("release_available") {
                            Text("Abort acknowledged. When you are satisfied the rig is safe, press ALLOW NEW SESSION, then ARM.")
                        } else if !status.string("release_unavailable_reason").isEmpty {
                            Text("Cannot release yet: \(status.string("release_unavailable_reason"))").foregroundStyle(.orange)
                        }
                    }
                }
            }
            Spacer()
            HStack {
                Button("ARM") { confirmation = .arm }
                    .disabled(model.busy || model.status == nil || !model.status!.bool("arm_available") || model.status!.bool("arm_blocked") || model.status!.bool("armed"))
                Button("DISARM") { confirmation = .disarm }
                    .disabled(model.busy || model.status == nil || !model.status!.bool("armed"))
                Button("ACKNOWLEDGE ABORT") { confirmation = .acknowledge }
                    .disabled(model.busy || model.status == nil || !model.status!.bool("incident_active") || model.status!.bool("acknowledged") || model.status!.string("incident_id").isEmpty)
                Button("ALLOW NEW SESSION") { confirmation = .release }
                    .disabled(model.busy || model.status == nil || !model.status!.bool("incident_active") || !model.status!.bool("acknowledged") || !model.status!.bool("release_available") || model.status!.string("incident_id").isEmpty)
            }
            Text("All commands go through Guardian's existing operator safety gate. No automatic rearm, restart, or power restoration.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(24).frame(minWidth: 700, minHeight: 620)
        .sheet(isPresented: $model.showSetup) { SetupWizard(status: model.status) }
        .task {
            while !Task.isCancelled {
                if !model.busy { await model.refresh() }
                try? await Task.sleep(for: .seconds(5))
            }
        }
        .confirmationDialog("Confirm Guardian action", isPresented: Binding(
            get: { confirmation != nil },
            set: { if !$0 { confirmation = nil } }
        ), titleVisibility: .visible) {
            if confirmation == .arm {
                Button("Confirm ARM") {
                    confirmation = nil
                    Task { await model.command(["command": "ARM", "confirmed": true]) }
                }
            } else if confirmation == .disarm {
                Button("Confirm DISARM") {
                    confirmation = nil
                    Task { await model.command(["command": "DISARM", "confirmed": true]) }
                }
            } else if confirmation == .acknowledge {
                Button("Acknowledge terminal ABORT", role: .destructive) {
                    confirmation = nil
                    guard let id = model.status?.string("incident_id"), !id.isEmpty else { return }
                    Task { await model.command(["command": "ACKNOWLEDGE_ABORT", "incident_id": id, "confirmed": true]) }
                }
            } else if confirmation == .release {
                Button("Allow a new session (release the abort)", role: .destructive) {
                    confirmation = nil
                    guard let id = model.status?.string("incident_id"), !id.isEmpty else { return }
                    Task { await model.command(["command": "RELEASE_ABORT", "incident_id": id, "confirmed": true]) }
                }
            }
            Button("Cancel", role: .cancel) { confirmation = nil }
        } message: {
            Text(confirmation == .acknowledge
                ? "Acknowledgment does not clear recovery, restore power, or ARM Guardian."
                : (confirmation == .release
                    ? "Releasing the abort does not ARM Guardian or restore power. ARM remains a separate step."
                    : "Guardian's safety interlocks remain authoritative."))
        }
        .alert("Guardian", isPresented: Binding(get: { model.notice != nil }, set: { if !$0 { model.notice = nil } })) {
            Button("OK") { model.notice = nil }
        } message: { Text(model.notice ?? "") }
    }
}

struct SetupWizard: View {
    @Environment(\.dismiss) private var dismiss
    let status: GuardianReply?
    @State private var selectedField = "asiair.timeout_seconds"
    @State private var proposedValue = ""
    @State private var previewResult: GuardianReply?
    @State private var previewError: String?
    @State private var previewBusy = false
    @State private var stageResult: GuardianReply?
    @State private var stageError: String?
    @State private var stageBusy = false
    private let options = [
        "asiair.ip_address", "asiair.timeout_seconds",
        "roof.stale_after_seconds", "roof.alpaca_host", "roof.alpaca_port",
        "roof.alpaca_device_number", "roof.alpaca_timeout_seconds",
        "kasa.power_strip_ip", "monitor.interval_seconds"
    ]
    private var setup: [String: Any]? { status?.raw["setup"] as? [String: Any] }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Guardian Setup · Inspection").font(.title.bold())
            Text("Read-only comparison with the running monitor. No settings are saved or activated.")
                .foregroundStyle(.secondary)
            if let setup = setup {
                if setup["available"] as? Bool == true {
                    LabeledContent("Installation YAML", value: "Loaded")
                    LabeledContent("Matches running monitor", value:
                        (setup["matches_active_monitor"] as? Bool == true) ? "Yes (checked fields only)" : "No")
                    if let sections = setup["sections"] as? [String: [String]] {
                        GroupBox("Configured fields (values hidden)") {
                            VStack(alignment: .leading, spacing: 6) {
                                ForEach(sections.keys.sorted(), id: \.self) { section in
                                    Text("\(section): \(sections[section, default: []].joined(separator: ", "))")
                                        .font(.caption)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    if let differences = setup["differences"] as? [String], !differences.isEmpty {
                        GroupBox("Differences from running monitor") {
                            VStack(alignment: .leading) {
                                ForEach(differences, id: \.self) { difference in
                                    Text(difference).foregroundStyle(.orange)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                } else {
                    Text(setup["reason"] as? String ?? "Configuration unavailable")
                        .foregroundStyle(.orange)
                }
            } else {
                Text("Installation inspection is not enabled in the Guardian monitor launch configuration.")
                    .foregroundStyle(.orange)
                Text("The monitor must be explicitly configured with --installation-config before this view can inspect YAML.")
                    .font(.caption)
            }
            GroupBox("Validate a proposed change · preview only") {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Enter a proposed value manually. Current endpoint values are deliberately hidden. No changes are saved.")
                        .font(.caption).foregroundStyle(.secondary)
                    Picker("Setting", selection: $selectedField) {
                        ForEach(options, id: \.self) { option in Text(option).tag(option) }
                    }
                    TextField("Proposed value", text: $proposedValue)
                        .textFieldStyle(.roundedBorder)
                        .onChange(of: proposedValue) { _, _ in previewResult = nil; stageResult = nil }
                        .onChange(of: selectedField) { _, _ in
                            proposedValue = ""
                            previewResult = nil
                            previewError = nil
                            stageResult = nil
                            stageError = nil
                        }
                    Button(previewBusy ? "Validating…" : "Validate proposed setting") {
                        Task { await preview() }
                    }
                    .disabled(previewBusy || proposedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || setup?["available"] as? Bool != true)
                    if let result = previewResult {
                        Text(result.ok ? "Preview accepted — NOT saved" : "Preview rejected")
                            .foregroundStyle(result.ok ? Color.primary : Color.orange)
                        Text(result.message).font(.caption)
                        if let differences = result.raw["differences"] as? [String], !differences.isEmpty {
                            Text("Active monitor differences: " + differences.joined(separator: ", "))
                                .font(.caption)
                        }
                    }
                    if previewResult?.ok == true, let digest = setup?["review_sha256"] as? String {
                        Button(stageBusy ? "Staging…" : "Review & Stage candidate (does NOT activate)") {
                            Task { await stage(digest: digest) }
                        }.disabled(stageBusy || previewBusy)
                        Text("Creates config.guardian-candidate.yaml beside active YAML. Existing candidate is never overwritten.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let result = stageResult {
                        Text(result.ok ? "Candidate staged — NOT activated" : "Staging rejected")
                            .foregroundStyle(result.ok ? Color.primary : Color.orange)
                        Text(result.message).font(.caption)
                    }
                    if let error = stageError { Text(error).font(.caption).foregroundStyle(.orange) }
                    if let error = previewError {
                        Text(error).foregroundStyle(.orange).font(.caption)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            Text("Only separate candidate staging is permitted. Activation and commissioning authorization remain disabled.")
                .font(.caption).foregroundStyle(.secondary)
            Spacer()
            HStack { Spacer(); Button("Close") { dismiss() } }
        }.padding(24).frame(minWidth: 600, minHeight: 520)
    }

    private func stage(digest: String) async {
        stageBusy = true
        defer { stageBusy = false }
        stageResult = nil
        stageError = nil
        let parts = selectedField.split(separator: ".").map(String.init)
        guard parts.count == 2 else { return }
        let value: Any
        if ["asiair.ip_address", "roof.alpaca_host", "kasa.power_strip_ip"].contains(selectedField) {
            value = proposedValue
        } else if ["roof.alpaca_port", "roof.alpaca_device_number"].contains(selectedField) {
            guard let n = Int(proposedValue) else { stageError = "Invalid integer"; return }
            value = n
        } else {
            guard let n = Double(proposedValue), n.isFinite else { stageError = "Invalid number"; return }
            value = n
        }
        let request: [String: Any] = ["command": "STAGE_SETUP",
            "changes": [parts[0]: [parts[1]: value]], "expected_sha256": digest]
        do {
            let path = guardianSocketPath
            stageResult = try await Task.detached { try sendGuardian(request, at: path) }.value
        } catch { stageError = error.localizedDescription }
    }

    private func preview() async {
        previewBusy = true
        defer { previewBusy = false }
        previewResult = nil
        previewError = nil
        let parts = selectedField.split(separator: ".").map(String.init)
        guard parts.count == 2 else { return }
        let value: Any
        if ["asiair.ip_address", "roof.alpaca_host", "kasa.power_strip_ip"].contains(selectedField) {
            value = proposedValue
        } else if ["roof.alpaca_port", "roof.alpaca_device_number"].contains(selectedField) {
            guard let parsed = Int(proposedValue) else {
                previewError = "Enter a whole number for this setting"
                return
            }
            value = parsed
        } else {
            guard let parsed = Double(proposedValue), parsed.isFinite else {
                previewError = "Enter a positive numeric value"
                return
            }
            value = parsed
        }
        let request: [String: Any] = [
            "command": "PREVIEW_SETUP",
            "changes": [parts[0]: [parts[1]: value]]
        ]
        do {
            let path = guardianSocketPath
            previewResult = try await Task.detached { try sendGuardian(request, at: path) }.value
        } catch {
            previewError = error.localizedDescription
        }
    }
}

final class GuardianAppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

@main struct GuardianDesktopApp: App {
    @NSApplicationDelegateAdaptor(GuardianAppDelegate.self) private var appDelegate
    var body: some Scene { WindowGroup("Guardian 1.0") { ContentView() } }
}
