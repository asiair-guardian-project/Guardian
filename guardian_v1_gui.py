"""Guardian 1.0 operator desktop GUI; IPC client only, never owns equipment."""
import argparse
import json
import os
from pathlib import Path
import socket
import tkinter as tk
from tkinter import messagebox, ttk

DEFAULT_SOCKET = Path.home() / 'Library/Application Support/GuardianV1/operator.sock'


def send_operator_request(path, request, timeout=2):
    """Send one bounded request to the existing serialized Guardian owner."""
    path = Path(path)
    if not path.is_socket():
        raise ConnectionError('Guardian operator service is not available')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(str(path))
        connection.sendall(json.dumps(request, separators=(',', ':')).encode() + b'\n')
        data = bytearray()
        while len(data) <= 16384:
            chunk = connection.recv(2048)
            if not chunk:
                break
            data.extend(chunk)
            if b'\n' in chunk:
                break
    if b'\n' not in data or len(data) > 16384:
        raise ValueError('Guardian returned an invalid or oversized response')
    response = json.loads(data.split(b'\n', 1)[0])
    if not isinstance(response, dict) or not isinstance(response.get('ok'), bool):
        raise ValueError('Guardian returned an invalid response')
    return response


class GuardianWindow:
    def __init__(self, root, socket_path):
        self.root = root
        self.socket_path = Path(socket_path)
        self.status = None
        root.title('Guardian 1.0 — Observatory Supervisor')
        root.minsize(560, 390)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Guardian 1.0', font=('Helvetica', 21, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Operator dashboard · Commands sent only to the Guardian runtime').pack(anchor='w', pady=(0, 18))
        self.connection = tk.StringVar(value='Connecting…')
        self.session = tk.StringVar(value='Unknown')
        self.arm = tk.StringVar(value='Unknown')
        self.recovery = tk.StringVar(value='Unknown')
        self.details = tk.StringVar(value='')
        for label, value in [('Connection', self.connection), ('Session', self.session), ('ARM', self.arm), ('Recovery', self.recovery)]:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=label, width=16).pack(side='left')
            ttk.Label(row, textvariable=value, wraplength=370).pack(side='left', fill='x')
        ttk.Separator(frame).pack(fill='x', pady=12)
        ttk.Label(frame, textvariable=self.details, wraplength=520, justify='left').pack(anchor='w', pady=(0, 15))
        controls = ttk.Frame(frame)
        controls.pack(anchor='w')
        self.arm_button = ttk.Button(controls, text='ARM', command=self.arm_action)
        self.arm_button.pack(side='left', padx=(0, 8))
        self.disarm_button = ttk.Button(controls, text='DISARM', command=self.disarm_action)
        self.disarm_button.pack(side='left', padx=(0, 8))
        self.ack_button = ttk.Button(controls, text='ACKNOWLEDGE ABORT', command=self.ack_action)
        self.ack_button.pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='Refresh', command=self.refresh).pack(side='left')
        ttk.Label(frame, text='Setup wizard and hardware authorization are not enabled in this release.', foreground='gray').pack(anchor='w', pady=(22, 0))
        self.refresh()

    def request(self, payload):
        try:
            return send_operator_request(self.socket_path, payload)
        except (OSError, ValueError, ConnectionError) as exc:
            messagebox.showerror('Guardian communication', str(exc))
            return None

    def refresh(self):
        try:
            status = send_operator_request(self.socket_path, {'command': 'STATUS'})
            if not status.get('ok') or status.get('code') != 'STATUS':
                raise ValueError('Guardian did not return operator status')
        except (OSError, ValueError, ConnectionError) as exc:
            self.status = None
            self.connection.set('Unavailable — ' + str(exc))
            self.session.set('Unknown')
            self.arm.set('Unknown')
            self.recovery.set('Unknown')
            self.details.set('No hardware control is available through this window.')
        else:
            self.status = status
            self.connection.set('Connected to Guardian operator service')
            self.session.set(str(status.get('session', 'Unknown')))
            self.arm.set('ARMED' if status.get('armed') else 'DISARMED')
            blocked = status.get('arm_blocked', True)
            self.recovery.set('ARM BLOCKED' if blocked else 'No active recovery block reported')
            parts = []
            if status.get('recovery_reason'):
                parts.append('Reason: ' + str(status['recovery_reason']))
            if status.get('incident_active'):
                parts.append('Active incident; acknowledged: ' + str(status.get('acknowledged')))
            if status.get('unresolved_actions'):
                parts.append('Unresolved: ' + ', '.join(map(str, status['unresolved_actions'])))
            self.details.set('\n'.join(parts) or 'No active incident reported by the operator service.')
        self.arm_button.configure(state='normal' if self.status and not self.status.get('arm_blocked', True) and not self.status.get('armed') else 'disabled')
        self.disarm_button.configure(state='normal' if self.status and self.status.get('armed') else 'disabled')
        self.ack_button.configure(state='normal' if self.status and self.status.get('incident_active') and not self.status.get('acknowledged') and self.status.get('incident_id') else 'disabled')
        self.root.after(5000, self.refresh)

    def arm_action(self):
        if not self.status or self.status.get('arm_blocked', True):
            return
        if messagebox.askyesno('Confirm ARM', 'Request ARM from the existing Guardian safety gate?'):
            self.show_result({'command': 'ARM', 'confirmed': True})

    def disarm_action(self):
        if messagebox.askyesno('Confirm DISARM', 'Revoke Guardian ARM authorization?'):
            self.show_result({'command': 'DISARM', 'confirmed': True})

    def ack_action(self):
        status = self.status
        if not status or not status.get('incident_active') or status.get('acknowledged'):
            return
        if messagebox.askyesno('Confirm terminal ABORT', 'Acknowledge this incident? This does not clear recovery, restore power, or ARM Guardian.'):
            self.show_result({'command': 'ACKNOWLEDGE_ABORT', 'incident_id': status['incident_id'], 'confirmed': True})

    def show_result(self, request):
        response = self.request(request)
        if response is not None:
            (messagebox.showinfo if response['ok'] else messagebox.showwarning)('Guardian', str(response.get('message', response.get('code', 'Unknown response'))))
            self.refresh()


def main():
    parser = argparse.ArgumentParser(description='Guardian 1.0 operator GUI')
    parser.add_argument('--socket', default=str(DEFAULT_SOCKET))
    args = parser.parse_args()
    root = tk.Tk()
    GuardianWindow(root, args.socket)
    root.mainloop()


if __name__ == '__main__':
    main()
