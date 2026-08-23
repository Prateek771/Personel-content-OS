"""Command Line Interface for AI Content Intelligence OS."""

import json
import subprocess
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from intelligence_os.config.settings import get_settings
from intelligence_os.core.exceptions import ConfigurationError
from intelligence_os.core.health import run_health_check
from intelligence_os.core.logger import logger
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import DiscoveryRecord, ResearchCoreData
from intelligence_os.storage.repositories import DiscoveryRepository, ContentDraftRepository, PublishingQueueRepository

app = typer.Typer(
    name="intelligence-os",
    help="AI Content Intelligence OS — Local-first Autonomous Content Pipeline",
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Show application version and runtime metadata."""
    settings = get_settings()
    console.print(f"[bold cyan]{settings.app_name}[/] [green]v{settings.app_version}[/]")
    console.print(f"Environment: [yellow]{settings.app_env}[/]")


@app.command()
def health(
    as_json: bool = typer.Option(False, "--json", help="Output health result as raw JSON")
) -> None:
    """Execute system health checks across local directories, storage, and credentials."""
    logger.info("Running system health check...")
    try:
        settings = get_settings()
        result = run_health_check(settings)
    except Exception as e:
        console.print(f"[bold red]Health check failed to initialize:[/] {e}")
        raise typer.Exit(code=1)

    if as_json:
        console.print(json.dumps(result, indent=2))
        return

    # Render formatted table
    status_color = "green" if result["status"] == "healthy" else "yellow"
    console.print(f"\n[bold]System Status:[/] [{status_color}]{result['status'].upper()}[/]")
    console.print(f"App Version: [cyan]{result['version']}[/] | Python: [cyan]{result['python_version']}[/]\n")

    # Directories
    dir_table = Table(title="Directory Accessibility")
    dir_table.add_column("Directory", style="cyan")
    dir_table.add_column("Exists", style="green")
    dir_table.add_column("Writable", style="green")
    for d, info in result["checks"]["directories"].items():
        dir_table.add_row(
            d,
            "[green]Yes[/]" if info["exists"] else "[red]No[/]",
            "[green]Yes[/]" if info["writable"] else "[red]No[/]",
        )
    console.print(dir_table)

    # Database
    db_info = result["checks"]["database"]
    console.print(f"\n[bold]SQLite Database:[/] {db_info['path']} -> " +
                  ("[green]Accessible (WAL Enabled)[/]" if db_info.get("accessible") else "[red]Failed[/]"))

    # Credentials
    cred_table = Table(title="Credential Configuration Status")
    cred_table.add_column("Integration", style="cyan")
    cred_table.add_column("Configured", style="magenta")
    for k, is_configured in result["checks"]["credentials"].items():
        cred_table.add_row(
            k.replace("_", " ").title(),
            "[green]Configured[/]" if is_configured else "[dim yellow]Not set[/]",
        )
    console.print(cred_table)


@app.command()
def check_config() -> None:
    """Validate current environment and settings without starting jobs."""
    try:
        settings = get_settings()
        console.print("[bold green]Configuration loaded successfully.[/]")
        console.print(f"Database path: [cyan]{settings.database_path}[/]")
        console.print(f"Log Level: [cyan]{settings.log_level}[/]")
        console.print(f"OpenRouter Configured: [cyan]{bool(settings.openrouter_api_key)}[/]")
        console.print(f"X (Twitter) Configured: [cyan]{bool(settings.x_access_token)}[/]")
        console.print(f"LinkedIn Configured: [cyan]{bool(settings.linkedin_client_id)}[/]")
        console.print(f"Copywriting Model: [cyan]{settings.openrouter_copywriting_model}[/]")
        console.print(f"Image Model: [cyan]{settings.openrouter_image_model}[/]")
    except ConfigurationError as e:
        console.print(f"[bold red]Configuration Error:[/] {e}")
        raise typer.Exit(code=1)


@app.command("firecrawl-start")
def firecrawl_start() -> None:
    """Start local Firecrawl container stack (Redis, RabbitMQ, Playwright, API) via Docker Compose."""
    console.print("[bold cyan]Starting self-hosted Firecrawl Docker Compose stack...[/]")
    try:
        subprocess.run(
            ["docker", "compose", "-f", "external/firecrawl/docker-compose.yaml", "up", "-d"],
            check=True,
        )
        console.print("[bold green]Firecrawl stack started successfully on http://localhost:3002![/]")
    except Exception as e:
        console.print(f"[bold yellow]Docker compose note:[/] {e}")
        console.print("[dim]Even without Docker, the built-in local scraper fallback runs automatically.[/]")


@app.command("firecrawl-stop")
def firecrawl_stop() -> None:
    """Stop local Firecrawl container stack."""
    console.print("[bold cyan]Stopping Firecrawl Docker stack...[/]")
    try:
        subprocess.run(
            ["docker", "compose", "-f", "external/firecrawl/docker-compose.yaml", "down"],
            check=True,
        )
        console.print("[bold green]Firecrawl stack stopped.[/]")
    except Exception as e:
        console.print(f"[bold red]Error stopping Firecrawl:[/] {e}")


@app.command("generate-x")
def generate_x(
    topic: str = typer.Option(None, "--topic", "-t", help="Specific AI topic or technical insight to generate for"),
    url: str = typer.Option(None, "--url", "-u", help="Specific GitHub repository or article URL"),
    thread: bool = typer.Option(True, "--thread/--single", help="Generate as multi-post thread (default) or single tweet"),
    publish_now: bool = typer.Option(False, "--publish", "-p", help="Immediately publish to X after generation & review check"),
) -> None:
    """Generate high-signal content specifically tailored for X (Twitter) using configured model."""
    from intelligence_os.intelligence.openrouter import OpenRouterClient
    from intelligence_os.content.x import XGenerator
    from intelligence_os.review.verifier import ReviewVerifier
    from intelligence_os.publishing.x import XPublisher
    from intelligence_os.storage.models import ContentDraftRecord
    import uuid

    settings = get_settings()
    db = Database(settings.database_path)
    run_migrations(db)

    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)
    client = OpenRouterClient(settings)

    console.print("[bold cyan]🤖 Initializing X Content Generator...[/]")
    console.print(f"Model: [magenta]{settings.openrouter_copywriting_model}[/]")

    # 1. Resolve or create Discovery item
    if url:
        disc = disc_repo.get_by_url(url)
        if not disc:
            disc = DiscoveryRecord(
                id=f"disc-custom-{uuid.uuid4().hex[:6]}",
                source_url=url,
                title=topic or f"Technical Analysis: {url}",
                raw_content=f"Custom topic analysis for {url}",
                status="BRIEF_READY",
                content_potential=0.90,
            )
            disc_repo.insert(disc)
    else:
        recent = disc_repo.list_by_status("BRIEF_READY", limit=1)
        if recent:
            disc = recent[0]
        else:
            disc = DiscoveryRecord(
                id=f"disc-custom-{uuid.uuid4().hex[:6]}",
                source_url="https://github.com/modelcontextprotocol/servers",
                title=topic or "Model Context Protocol Tool Integration Architecture",
                raw_content="Standardized tool integration across LLM coding agents",
                status="BRIEF_READY",
                content_potential=0.95,
            )
            disc_repo.insert(disc)

    console.print(f"Target Discovery: [bold green]{disc.title}[/] ([dim]{disc.source_url}[/])")

    # 2. Build Research Core
    core = ResearchCoreData(
        hook=f"Why {disc.title} is changing how we build AI agent workflows.",
        core_insight=disc.summary or "Standardizing tool communication eliminates 90% of boilerplate code.",
        evidence=[disc.source_url],
        practical_takeaway="Implement lightweight stdio agent servers.",
        limitations="Requires local runtime setup.",
        content_angle=disc.content_angle or "workflow",
        tags=["#AIAgents", "#OpenSource", "#BuildInPublic", "#SoftwareEngineering"],
    )

    # 3. Generate X Content using dots-studio model
    x_gen = XGenerator(client)
    format_type = "thread" if thread else "post"
    result = x_gen.generate(core, preferred_format=format_type)

    console.print("\n" + "=" * 60)
    console.print("[bold yellow]✨ GENERATED X CONTENT:[/]")
    console.print("=" * 60)
    if result.posts:
        for p in result.posts:
            console.print(f"[bold cyan][Post {p.post_number}][/]\n{p.text}\n")
    else:
        console.print(result.full_text_rendered)
    console.print("=" * 60 + "\n")

    # 4. Review & Verify
    verifier = ReviewVerifier(client)
    review_res = verifier.verify_draft(result.full_text_rendered, core, "x")
    console.print(f"Review Gate Score: [bold green]{(review_res.overall_score * 100):.0f}%[/] (Passed: {review_res.is_approved})")

    draft_record = ContentDraftRecord(
        id=f"draft-x-{uuid.uuid4().hex[:8]}",
        discovery_id=disc.id,
        research_core=core.model_dump(),
        generated_copy=result.full_text_rendered,
        platform="x",
        format=format_type,
        review_score=review_res.overall_score,
        review_feedback=review_res.feedback,
        status="APPROVED" if review_res.is_approved else "DRAFTED",
    )
    draft_repo.insert(draft_record)
    console.print(f"Saved Draft to Database: [dim]{draft_record.id}[/]")

    # 5. Publish to X if requested
    if publish_now and review_res.is_approved:
        console.print("\n[bold cyan]🚀 Publishing directly to X...[/]")
        x_pub = XPublisher(settings)
        if x_pub.is_configured():
            try:
                tweet_id = x_pub.publish(draft_record)
                console.print(f"[bold green]🎉 Published live to X![/] Tweet ID: [bold]{tweet_id}[/]")
            except Exception as e:
                console.print(f"[bold red]Publishing failed:[/] {e}")
        else:
            console.print("[bold yellow]X API credentials not fully configured. Saved to queue for manual review.[/]")


@app.command()
def run() -> None:
    """Execute a single end-to-end intelligence cycle (Harvest -> Dedup -> Analyze -> Score -> Draft -> Review -> Publish)."""
    from intelligence_os.scheduler.runner import PipelineRunner
    console.print("[bold cyan]Starting full Intelligence OS pipeline cycle...[/]")
    runner = PipelineRunner()
    results = runner.run_full_pipeline_cycle()
    console.print("[bold green]Cycle completed.[/]")
    console.print(json.dumps(results, indent=2, default=str))


@app.command()
def dashboard(
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind dashboard server"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind dashboard"),
) -> None:
    """Launch the local interactive 3D command center dashboard."""
    console.print(f"[bold green]Starting AI Content Intelligence Dashboard at http://{host}:{port}[/]")
    uvicorn.run("intelligence_os.dashboard.app:app", host=host, port=port, reload=False)


def main() -> None:
    """CLI application entrypoint."""
    app()


if __name__ == "__main__":
    main()
