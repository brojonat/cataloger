"""CLI for cataloger."""

import base64
import os
import shutil
import sys
from pathlib import Path

import click
import yaml

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def cli() -> None:
    """Cataloger command line interface."""
    pass


@cli.group()
def admin() -> None:
    """Administrative and setup commands."""
    pass


@admin.command("encode-prompt")
@click.argument("prompt_file", type=click.Path(exists=True))
def encode_prompt(prompt_file: str) -> None:
    """Encode a prompt YAML file to base64 for use in environment variables.

    Example:
        cataloger admin encode-prompt prompts/cataloging_agent.yaml
    """
    with open(prompt_file, "r") as f:
        content = f.read()

    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    click.echo(encoded)


@admin.command("setup-env")
def setup_env() -> None:
    """Setup environment configuration for Cataloger.

    Idempotent command that creates/updates .env.server with encoded prompts.
    Safe to run multiple times - will always update prompts to latest version.

    """
    # Check if prompts exist
    prompts_dir = Path("prompts")
    cataloging_prompt_file = prompts_dir / "cataloging_agent.yaml"
    summary_prompt_file = prompts_dir / "summary_agent.yaml"

    if not cataloging_prompt_file.exists():
        click.echo(f"✗ Error: {cataloging_prompt_file} not found", err=True)
        sys.exit(1)

    if not summary_prompt_file.exists():
        click.echo(f"✗ Error: {summary_prompt_file} not found", err=True)
        sys.exit(1)

    env_file = Path(".env.server")

    # Encode prompts
    click.echo("📝 Encoding prompts...")
    with open(cataloging_prompt_file) as f:
        data = yaml.safe_load(f)
        prompt = data["prompt"]
        cataloging_encoded = base64.b64encode(prompt.encode("utf-8")).decode("utf-8")

    with open(summary_prompt_file) as f:
        data = yaml.safe_load(f)
        prompt = data["prompt"]
        summary_encoded = base64.b64encode(prompt.encode("utf-8")).decode("utf-8")

    # Determine if we're creating new or updating existing
    if env_file.exists():
        click.echo("✓ Updating existing .env.server")

        # Read existing file
        with open(env_file) as f:
            lines = f.readlines()

        # Update prompt lines, preserve everything else
        updated = []
        cataloging_updated = False
        summary_updated = False

        for line in lines:
            if line.startswith("CATALOGING_AGENT_PROMPT="):
                updated.append(f'CATALOGING_AGENT_PROMPT="{cataloging_encoded}"\n')
                cataloging_updated = True
            elif line.startswith("SUMMARY_AGENT_PROMPT="):
                updated.append(f'SUMMARY_AGENT_PROMPT="{summary_encoded}"\n')
                summary_updated = True
            else:
                updated.append(line)

        # If prompts weren't in file, append them
        if not cataloging_updated:
            updated.append(f'CATALOGING_AGENT_PROMPT="{cataloging_encoded}"\n')
        if not summary_updated:
            updated.append(f'SUMMARY_AGENT_PROMPT="{summary_encoded}"\n')

        # Write back
        with open(env_file, "w") as f:
            f.writelines(updated)

        click.echo("✓ Prompts updated in .env.server")

    else:
        # Create new file from template
        template_file = Path(".env.server.example")
        storage_type = "s3"

        if not template_file.exists():
            click.echo(f"✗ Error: Template {template_file} not found", err=True)
            sys.exit(1)

        # Copy template
        shutil.copy(template_file, env_file)
        click.echo(f"✓ Created .env.server from {template_file.name}")

        # Update with encoded prompts
        with open(env_file) as f:
            content = f.read()

        content = content.replace(
            'export CATALOGING_AGENT_PROMPT=""',
            f'export CATALOGING_AGENT_PROMPT="{cataloging_encoded}"',
        )
        content = content.replace(
            'export SUMMARY_AGENT_PROMPT=""',
            f'export SUMMARY_AGENT_PROMPT="{summary_encoded}"',
        )

        with open(env_file, "w") as f:
            f.write(content)

        click.echo("✓ Prompts encoded and added to .env.server")
        click.echo("")
        click.echo(f"📦 Storage configured for: {storage_type}")

    click.echo("")
    click.echo("🎯 Next steps:")
    click.echo("  1. Edit .env.server and set:")
    click.echo("     - LLM_API_KEY (your LLM provider API key)")
    click.echo("     - S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
    click.echo("  2. Run local services if needed: ./scripts/start-dev-services.sh")
    click.echo("  3. Build container: ./scripts/build-container.sh")
    click.echo("  4. Create databases: ./scripts/bootstrap-db.sh")
    click.echo("  5. Start server: ./scripts/run-server.sh")
    click.echo("")
    click.echo("💡 Tip: Run this command again anytime to update prompts!")


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
        click.echo(
            "Error: Missing API URL (use --api-url or CATALOGER_API_URL)", err=True
        )
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
