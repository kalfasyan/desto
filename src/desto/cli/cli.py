"""Entry point for desto-cli."""


def cli_main():
    """Run the desto CLI."""
    from desto.cli.main import app

    app()


if __name__ == "__main__":
    cli_main()
