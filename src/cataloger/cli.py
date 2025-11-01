"""CLI for cataloger."""

import base64
import os
import sys
from pathlib import Path

import click
import yaml

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def cli() -> None:
    """Cataloger command line interface."""
    pass


@cli.command()
@click.argument("prompt_file", type=click.Path(exists=True))
def encode_prompt(prompt_file: str) -> None:
    """Encode a prompt YAML file to base64 for use in environment variables.

    Example:
        cataloger encode-prompt prompts/cataloging_agent.yaml
    """
    with open(prompt_file, "r") as f:
        content = f.read()

    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    click.echo(encoded)


@cli.command()
@click.option("--db-conn", required=True, help="Database connection string")
@click.option("--tables", required=True, help="Comma-separated list of tables")
@click.option("--s3-prefix", required=True, help="S3 prefix for output")
@click.option("--api-url", help="API URL (defaults to env CATALOGER_API_URL)")
@click.option("--token", help="Auth token (defaults to env CATALOGER_AUTH_TOKEN)")
def catalog(
    db_conn: str,
    tables: str,
    s3_prefix: str,
    api_url: str | None,
    token: str | None,
) -> None:
    """Trigger a catalog generation.

    Example:
        cataloger catalog \\
          --db-conn "postgresql://user:pass@host:5432/db" \\
          --tables "users,orders,products" \\
          --s3-prefix "customer-123/prod"
    """
    import requests

    api_url = api_url or os.getenv("CATALOGER_API_URL")
    token = token or os.getenv("CATALOGER_AUTH_TOKEN")

    if not api_url:
        click.echo("Error: Missing API URL (use --api-url or CATALOGER_API_URL)", err=True)
        sys.exit(1)

    if not token:
        click.echo(
            "Error: Missing auth token (use --token or CATALOGER_AUTH_TOKEN)", err=True
        )
        sys.exit(1)

    # Parse tables
    table_list = [t.strip() for t in tables.split(",")]

    # Make request
    response = requests.post(
        f"{api_url}/catalog",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "db_connection_string": db_conn,
            "tables": table_list,
            "s3_prefix": s3_prefix,
        },
    )

    if response.status_code == 200:
        result = response.json()
        click.echo(f"✓ Catalog generated successfully")
        click.echo(f"  Timestamp: {result['timestamp']}")
        click.echo(f"  Catalog:   {result['catalog_uri']}")
        click.echo(f"  Summary:   {result['summary_uri']}")
    else:
        click.echo(f"✗ Error: {response.status_code}", err=True)
        click.echo(response.text, err=True)
        sys.exit(1)


@cli.command()
@click.argument("secret", required=False)
def generate_token(secret: str | None) -> None:
    """Generate a test JWT token for development.

    Example:
        cataloger generate-token your-secret-key
    """
    from jose import jwt

    secret = secret or os.getenv("AUTH_SECRET", "change-me")

    token = jwt.encode(
        {"sub": "dev-user", "role": "admin"},
        secret,
        algorithm="HS256",
    )

    click.echo(token)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
