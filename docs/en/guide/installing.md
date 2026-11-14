# Installing

## Python

bisim.py needs Python 3.9 or newer. Check the version you have:

```sh
python --version
```

On Windows the launcher is `py`, so `py --version` works too. If the command is missing or the version is
older, install the latest Python from [python.org](https://www.python.org/downloads/).

## A virtual environment

Give each bot its own virtual environment, so its packages do not mix with other projects.

=== "Linux and macOS"

    ```sh
    mkdir my-bot
    cd my-bot
    python3 -m venv .venv
    source .venv/bin/activate
    ```

=== "Windows (PowerShell)"

    ```powershell
    mkdir my-bot
    cd my-bot
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    ```

=== "Windows (cmd)"

    ```bat
    mkdir my-bot
    cd my-bot
    py -m venv .venv
    .venv\Scripts\activate.bat
    ```

While the environment is active, `python` and `pip` are the ones inside `.venv`. Run `deactivate` to leave it.

## Install bisim.py

```sh
pip install bisim.py
```

The package is called `bisim.py` on PyPI and is imported as `bisim`. It brings in
[aiohttp](https://docs.aiohttp.org), which it uses for both the REST API and the gateway.

## Optional extras

| Extra | Install with | What it adds |
| --- | --- | --- |
| `http` | `pip install "bisim.py[http]"` | PyNaCl, to check the signatures of interactions sent to an [Interactions URL](topics/interactions-url.md) |
| `speed` | `pip install "bisim.py[speed]"` | orjson, a faster JSON parser the library uses when it is installed |

Extras can be combined: `pip install "bisim.py[http,speed]"`. A bot that receives interactions over the
gateway, which is what most bots do, needs neither.

## Check the installation

```sh
python -c "import bisim; print(bisim.__version__)"
```

This prints the installed version, for example `0.1.0`. `bisim.version_info` holds the same version as a named
tuple, for comparisons in code.

## Upgrading

```sh
pip install --upgrade bisim.py
```

Read the [changelog](https://github.com/bisim-gg/bisim.py/blob/main/CHANGELOG.md) before upgrading a bot
that already runs.

Next: [creating your application](creating-an-application.md).
