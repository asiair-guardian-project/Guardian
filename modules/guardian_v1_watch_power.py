"""READ-ONLY power-strip reader for the monitoring watch.

Only get_outlet_states is ever called; nothing here can switch an outlet.
"""


def make_reader(kasa_host, requests):
    from modules.kasa_controller import KasaController
    from modules.kasa_safety_power_adapter import PythonKasaTransport

    user, password = KasaController(kasa_host)._credentials()
    transport = PythonKasaTransport(host=kasa_host, username=user, password=password)
    requests = list(requests)

    def read():
        return transport.get_outlet_states(requests)

    return read
