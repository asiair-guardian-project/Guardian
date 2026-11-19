"""Read-only Kasa endpoint validation for Guardian 1.0 shadow mode."""


class KasaReadOnlyAdapter:
    """Expose only endpoint identity checks, never power switching."""

    def __init__(self, *, controller_id, endpoints, transport):
        self._controller_id = controller_id
        self._endpoints = dict(endpoints)
        self._transport = transport

    @property
    def controller_id(self):
        return self._controller_id

    def check_endpoint(self, endpoint):
        if endpoint.controller_id != self._controller_id:
            return False

        config = self._endpoints.get(endpoint.endpoint_id)

        if config is None:
            return False

        return self._transport.check_outlet(
            config.outlet_number,
            config.expected_alias,
        )
