The following secrets are available

ARM_SUBSCRIPTION_ID
ARM_CLIENT_SECRET
ARM_TENANT_ID
ARM_CLIENT_ID

You can gain the use of az cli with the following preamble

az login --service-principal \
  --username "$ARM_CLIENT_ID" \
  --password "$ARM_CLIENT_SECRET" \
  --tenant "$ARM_TENANT_ID"

az account set --subscription "$ARM_SUBSCRIPTION_ID"

If you need az, you will first need to install the cli using:

curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

## Firecrawl utilities

Two helper scripts are available in the project root:

* **web_search.py** – search the web using Firecrawl. Usage:
  `./web_search.py <query>`
* **get_url.py** – scrape a URL and output markdown. Usage:
  `./get_url.py <url>`

Set your API key in the ``FIRECRAWL_API_KEY`` environment variable before
running either script.

Both scripts require the `firecrawl-py` package which is listed in
`agents/requirements-worker.txt`.

## Setup

Before running tasks in this repository, install the Python dependencies with:

```bash
pip install -r agents/requirements-worker.txt
```

Run this command from the project root so all utilities work correctly.
