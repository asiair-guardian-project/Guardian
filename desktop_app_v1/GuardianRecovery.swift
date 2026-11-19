import Cocoa
import Darwin

// Guardian v1 operator recovery viewer. Read-only by construction.
// Never reads or writes the legacy guardian_control.txt command channel.
final class RecoveryAppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var headline: NSTextField!
    private var summary: NSTextField!
    private var details: NSTextView!
    private var fileLabel: NSTextField!
    private var timer: Timer?
    private var ackButton: NSButton!
    private var activeToken: String?
    private var socketURL: URL?
    private var notified = false
    private let recoveryURL: URL

    init(recoveryURL: URL, socketURL: URL?) {
        self.recoveryURL = recoveryURL
        self.socketURL = socketURL
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let frame = NSRect(x: 0, y: 0, width: 650, height: 525)
        window = NSWindow(contentRect: frame,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Guardian 1.0 — Operator Recovery"
        window.center()
        window.minSize = NSSize(width: 560, height: 440)

        let root = NSStackView()
        root.orientation = .vertical
        root.alignment = .leading
        root.spacing = 12
        root.translatesAutoresizingMaskIntoConstraints = false
        root.edgeInsets = NSEdgeInsets(top: 20, left: 22, bottom: 20, right: 22)

        headline = NSTextField(labelWithString: "RECOVERY STATUS UNKNOWN — ARM NOT ASSESSED")
        headline.font = .boldSystemFont(ofSize: 18)
        headline.textColor = .systemRed
        headline.lineBreakMode = .byWordWrapping
        headline.maximumNumberOfLines = 2

        summary = NSTextField(wrappingLabelWithString: "Waiting for recovery snapshot")
        summary.font = .systemFont(ofSize: 14)

        fileLabel = NSTextField(wrappingLabelWithString: "Recovery file: \(recoveryURL.path)")
        fileLabel.font = .systemFont(ofSize: 11)
        fileLabel.textColor = .secondaryLabelColor

        details = NSTextView()
        details.isEditable = false
        details.isSelectable = true
        details.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        details.textContainerInset = NSSize(width: 10, height: 10)
        let scroll = NSScrollView()
        scroll.documentView = details
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder

        ackButton = NSButton(title: "ACKNOWLEDGE ABORT", target: self, action: #selector(acknowledgeAbort))
        // A distinct, centered action button rather than a full-width banner.
        ackButton.isBordered = false
        ackButton.wantsLayer = true
        ackButton.layer?.backgroundColor = NSColor.systemRed.cgColor
        ackButton.layer?.cornerRadius = 10
        ackButton.contentTintColor = .white
        ackButton.font = .boldSystemFont(ofSize: 15)
        ackButton.toolTip = "Confirm that you have reviewed the abort. Does not clear the incident."
        ackButton.isHidden = true
        ackButton.isEnabled = false

        let footer = NSTextField(wrappingLabelWithString:
            "Acknowledgment does NOT clear the incident or permit ARM. " +
            "Saved results are NOT fresh hardware verification.")
        footer.font = .systemFont(ofSize: 11)
        footer.textColor = .secondaryLabelColor

        for view in [headline!, summary!, fileLabel!, scroll, ackButton!, footer] {
            view.translatesAutoresizingMaskIntoConstraints = false
            root.addArrangedSubview(view)
            if view === ackButton {
                NSLayoutConstraint.activate([
                    view.centerXAnchor.constraint(equalTo: root.centerXAnchor),
                    view.widthAnchor.constraint(equalToConstant: 280),
                    view.heightAnchor.constraint(equalToConstant: 48)
                ])
            } else {
                NSLayoutConstraint.activate([
                    view.leadingAnchor.constraint(equalTo: root.leadingAnchor),
                    view.trailingAnchor.constraint(equalTo: root.trailingAnchor)
                ])
            }
        }
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 235).isActive = true
        scroll.setContentHuggingPriority(.defaultLow, for: .vertical)
        window.contentView?.addSubview(root)
        NSLayoutConstraint.activate([
            root.topAnchor.constraint(equalTo: window.contentView!.topAnchor),
            root.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor),
            root.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor)
        ])
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            self?.refresh()
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func failClosed(_ message: String) {
        headline.stringValue = "RECOVERY STATUS UNKNOWN — ARM NOT ASSESSED"
        headline.textColor = .systemRed
        summary.stringValue = "Recovery file unavailable or invalid. Do not treat this display as permission to ARM."
        details.string = message
        ackButton.isHidden = true
        activeToken = nil
    }

    private func socketRequest(_ request: [String: Any]) -> [String: Any]? {
        guard let path = socketURL?.path, path.utf8.count < 100 else { return nil }
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        defer { Darwin.close(fd) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8CString)
        withUnsafeMutableBytes(of: &address.sun_path) { raw in
            for (i, byte) in bytes.enumerated() { raw[i] = UInt8(bitPattern: byte) }
        }
        let connected = withUnsafePointer(to: &address) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard connected == 0,
              let data = try? JSONSerialization.data(withJSONObject: request) else { return nil }
        let outgoing = data + Data([10])
        let sent = outgoing.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, outgoing.count) }
        guard sent == outgoing.count else { return nil }
        var response = Data()
        var buffer = [UInt8](repeating: 0, count: 1024)
        while response.count < 8192 {
            let n = Darwin.read(fd, &buffer, buffer.count)
            if n <= 0 { break }
            response.append(contentsOf: buffer.prefix(n))
            if response.contains(10) { break }
        }
        guard let firstLine = response.split(separator: 10).first else { return nil }
        return (try? JSONSerialization.jsonObject(with: Data(firstLine))) as? [String: Any]
    }

    @objc private func acknowledgeAbort() {
        guard let token = activeToken else { return }
        let alert = NSAlert()
        alert.messageText = "Acknowledge Guardian ABORT?"
        alert.informativeText = "This records your acknowledgment only. It does NOT clear the incident, stop shutdown retries, restore power, or permit ARM."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "ACKNOWLEDGE ABORT")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let response = socketRequest(["command": "ACKNOWLEDGE_ABORT", "incident_id": token, "confirmed": true])
        let result = NSAlert()
        result.messageText = (response?["ok"] as? Bool == true) ? "Acknowledgment saved" : "Acknowledgment NOT saved"
        result.informativeText = response?["message"] as? String ?? "Guardian operator service unavailable. The incident remains latched."
        result.runModal()
        refresh()
    }

    private func refresh() {
        do {
            let data = try Data(contentsOf: recoveryURL)
            guard let state = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let version = state["schema_version"] as? Int, version == 2,
                  let session = state["session_state"] as? String,
                  let required = state["recovery_required"] as? Bool,
                  let acknowledged = state["abort_acknowledged"] as? Bool,
                  let clean = state["shutdown_clean"] as? Bool,
                  let history = state["incident_history"] as? [Any],
                  let incidentValue = state["active_incident"] else {
                failClosed("Recovery snapshot is missing required fields or uses an unsupported schema.")
                return
            }
            let incident = incidentValue as? [String: Any]
            if !(incidentValue is NSNull) && incident == nil {
                failClosed("Malformed active incident record.")
                return
            }
            let interrupted = !clean && session != "DISARMED"
            let blocked = required || incident != nil || interrupted
            if blocked {
                headline.stringValue = "GUARDIAN — RECOVERY REQUIRED / ARM BLOCKED"
                headline.textColor = .systemRed
            } else {
                headline.stringValue = "NO PERSISTED RECOVERY LATCH"
                headline.textColor = .labelColor
            }
            summary.stringValue = "Saved session: \(session)   |   ABORT acknowledged: \(acknowledged ? "YES" : "NO")"
            var lines = [
                "Snapshot status: \(blocked ? "RECOVERY REQUIRED" : "No saved recovery latch")",
                "Saved session: \(session)",
                "Clean shutdown marker: \(clean ? "YES" : "NO")",
                "Historical incidents: \(history.count)",
                ""
            ]
            if let incident = incident {
                guard let triggers = incident["triggers"] as? [String],
                      let plan = incident["plan"] as? [String],
                      let records = incident["records"] as? [[String: String]] else {
                    failClosed("Malformed incident details.")
                    return
                }
                lines.append("ABORT TRIGGERS: \(triggers.joined(separator: ", "))")
                lines.append("PROTECTION ACTIONS (saved results; not live readings):")
                for action in plan {
                    let matches = records.filter { $0["action"] == action }
                    let result = matches.last?["result"] ?? "NOT VERIFIED"
                    lines.append("  \(action): \(result)")
                }
                lines.append("")
                lines.append(acknowledged ? "Operator acknowledged; incident still latched." : "Operator acknowledgment required.")
            } else {
                lines.append("No active incident in this saved snapshot.")
            }
            lines.append("\nWARNING: Saved results are not fresh hardware verification.")
            details.string = lines.joined(separator: "\n")
            // The socket belongs to the running Guardian process; the file is display-only.
            activeToken = nil
            ackButton.isHidden = true
            if incident != nil && !acknowledged && socketURL != nil {
                if let status = socketRequest(["command": "STATUS"]),
                   status["ok"] as? Bool == true,
                   status["incident_active"] as? Bool == true,
                   status["recovery_file"] as? String == recoveryURL.standardizedFileURL.path,
                   status["acknowledged"] as? Bool == false,
                   let token = status["incident_id"] as? String,
                   token.count == 64 {
                    activeToken = token
                    ackButton.isHidden = false
                    ackButton.isEnabled = true
                }
            }
            if blocked && incident != nil && !notified {
                notified = true
                let script = "display notification \"Open Guardian Recovery to review the unresolved incident.\" with title \"Guardian — Recovery Required\""
                let task = Process()
                task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
                task.arguments = ["-e", script]
                try? task.run()
            }
        } catch {
            failClosed("Unable to read recovery file: \(error.localizedDescription)")
        }
    }
}

// Explicit recovery-file argument prevents accidentally reading legacy state.
// The file is never created or modified by this viewer.
let arguments = CommandLine.arguments
if (arguments.count != 2 && arguments.count != 3) || arguments[1].hasPrefix("-") {
    fputs("Usage: GuardianRecovery <absolute-path-to-v1-recovery.json> [absolute-path-to-operator.sock]\n", stderr)
    exit(2)
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let socketURL = arguments.count == 3 ? URL(fileURLWithPath: arguments[2]) : nil
let delegate = RecoveryAppDelegate(recoveryURL: URL(fileURLWithPath: arguments[1]), socketURL: socketURL)
app.delegate = delegate
app.run()
