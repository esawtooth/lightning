import json
import datetime
import requests
from pulumi import dynamic


class GoDaddyNameServerProvider(dynamic.ResourceProvider):
    def create(self, inputs):
        domain = inputs["domain"]
        nameservers = inputs["nameservers"]
        api_key = inputs["apiKey"]
        api_secret = inputs["apiSecret"]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"sso-key {api_key}:{api_secret}",
        }
        body = {
            "nameservers": nameservers,
            # GoDaddy requires consent when updating nameservers
            "consent": {
                "agreedAt": datetime.datetime.utcnow().isoformat() + "Z",
                "agreedBy": "127.0.0.1",
                "agreementKeys": ["DNRA"],
            },
        }
        url = f"https://api.godaddy.com/v1/domains/{domain}/nameservers"
        resp = requests.put(url, headers=headers, data=json.dumps(body))
        resp.raise_for_status()
        return dynamic.CreateResult(domain, inputs)

    def delete(self, id, props):
        # We don't revert nameserver changes on delete
        pass


class GoDaddyNameServers(dynamic.Resource):
    def __init__(self, name, domain, nameservers, api_key, api_secret, opts=None):
        super().__init__(
            GoDaddyNameServerProvider(),
            name,
            {
                "domain": domain,
                "nameservers": nameservers,
                "apiKey": api_key,
                "apiSecret": api_secret,
            },
            opts,
        )
