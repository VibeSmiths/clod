"""Capture Rich CLI output as SVG screenshots for README documentation.

Usage::

    python scripts/capture_screenshots.py

Generates SVG files in assets/ that can be embedded in README.md.
"""

from __future__ import annotations

import io
import sys
import pathlib

# Add project root to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.text import Text


def make_console(width: int = 100) -> Console:
    # Write to StringIO to avoid Windows encoding issues with Unicode
    return Console(record=True, width=width, file=io.StringIO(), force_terminal=True)


def save(c: Console, name: str, title: str = "clod") -> None:
    svg = c.export_svg(title=title)
    dest = pathlib.Path(__file__).parent.parent / "assets" / f"{name}.svg"
    dest.write_text(svg, encoding="utf-8")
    print(f"  Saved {dest.name}")


# ── 1. Help ─────────────────────────────────────────────────────────────────


def capture_help():
    c = make_console()
    pipeline_rows = "\n".join(
        [
            "  code_review    qwen2.5-coder:14b                    → claude-sonnet",
            "  reason_review  deepseek-r1:14b                      → claude-sonnet",
            "  chat_assist    llama3.1:8b                          → claude-haiku",
        ]
    )
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold cyan]Slash commands:[/bold cyan]",
                    "  [yellow]/model [/yellow][dim]<name>[/dim]          switch model (ollama or litellm alias)",
                    "  [yellow]/pipeline [/yellow][dim]<name|off>[/dim]   use a two-stage pipeline",
                    "  [yellow]/tools [/yellow][dim][on|off][/dim]         toggle tool use",
                    "  [yellow]/offline [/yellow][dim][on|off][/dim]       toggle offline mode (local only)",
                    "  [yellow]/search [/yellow][dim][on|off][/dim]        toggle web search (SearXNG)",
                    "  [yellow]/tokens[/yellow]                  show session Claude token usage",
                    "  [yellow]/system [/yellow][dim]<prompt>[/dim]        set system prompt",
                    "  [yellow]/clear[/yellow]                   clear conversation history",
                    "  [yellow]/save [/yellow][dim]<file>[/dim]            save conversation to JSON",
                    "  [yellow]/index [/yellow][dim][path][/dim]           index projects: generate CLAUDE.md + README",
                    "  [yellow]/gpu[/yellow]                     show GPU VRAM + optimal model recommendation",
                    "  [yellow]/mcp[/yellow]                     show MCP filesystem server status and endpoints",
                    "  [yellow]/generate [/yellow][dim][image|video] <prompt>[/dim]  generate image or video from description",
                    "  [yellow]/sd [/yellow][dim][image|video|stop|start][/dim]  switch image/video mode or stop/start SD",
                    "  [yellow]/services[/yellow]               show docker service health status",
                    "  [yellow]/intent[/yellow]                  show current intent classification state",
                    "  [yellow]/intent auto[/yellow]             re-enable auto-classification",
                    "  [yellow]/intent verbose[/yellow]          toggle verbose intent debug output",
                    "  [yellow]/intent [/yellow][dim]<text>[/dim]          one-shot classify text",
                    "  [yellow]/services start[/yellow]         start missing core services via docker compose",
                    "  [yellow]/services stop[/yellow]          stop all core services (docker compose down)",
                    "  [yellow]/services reset [/yellow][dim][name|all][/dim]  wipe data and redeploy service(s)",
                    "  [yellow]/help[/yellow]                    show this message",
                    "  [yellow]/exit[/yellow] or [yellow]/quit[/yellow]            exit clod",
                    "",
                    "[bold cyan]Pipelines (local → claude):[/bold cyan]",
                    pipeline_rows,
                ]
            ),
            title="[cyan]help[/cyan]",
            border_style="cyan",
        )
    )
    save(c, "help")


# ── 2. Header — default ────────────────────────────────────────────────────


def capture_header_default():
    c = make_console()
    c.print(
        Panel(
            "[bold cyan]clod[/bold cyan] [dim]v1.0.0[/dim]  •  "
            "[bold]qwen2.5-coder:14b[/bold]  •  tools: [dim]off[/dim]  •  [dim]online[/dim]  •  [dim]search: off[/dim]\n"
            "[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "header_default")


# ── 3. Header — pipeline active ────────────────────────────────────────────


def capture_header_pipeline():
    c = make_console()
    c.print(
        Panel(
            "[bold cyan]clod[/bold cyan] [dim]v1.0.0[/dim]  •  "
            "[bold]pipeline:code_review[/bold]  •  tools: [green]on[/green]  •  [dim]online[/dim]  •  [green]search: on[/green]\n"
            "[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "header_pipeline")


# ── 4. Header — token budget warning ──────────────────────────────────────


def capture_header_tokens():
    c = make_console()
    c.print(
        Panel(
            "[bold cyan]clod[/bold cyan] [dim]v1.0.0[/dim]  •  "
            "[bold]claude-sonnet[/bold]  •  tools: [green]on[/green]  •  [dim]online[/dim]  •  [green]search: on[/green]  •  "
            "tokens: [yellow]45,200 / 100,000 (45%)[/yellow]\n"
            "[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "header_tokens")


# ── 5. Header — offline mode ──────────────────────────────────────────────


def capture_header_offline():
    c = make_console()
    c.print(
        Panel(
            "[bold cyan]clod[/bold cyan] [dim]v1.0.0[/dim]  •  "
            "[bold]qwen2.5-coder:14b[/bold]  •  tools: [green]on[/green]  •  [bold red]OFFLINE[/bold red]  •  [dim]search: off[/dim]  •  "
            "tokens: [red]86,400 / 100,000 (86%)[/red]\n"
            "[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "header_offline")


# ── 6. Services status ───────────────────────────────────────────────────


def capture_services():
    c = make_console()
    dot_up = "[green]●[/green]"
    dot_dn = "[red]●[/red]"
    c.print(
        Panel(
            "\n".join(
                [
                    f"  {dot_up} ollama          http://localhost:11434    [green]healthy[/green]",
                    f"  {dot_up} litellm         http://localhost:4000     [green]healthy[/green]",
                    f"  {dot_up} pipelines       http://localhost:9099     [green]healthy[/green]",
                    f"  {dot_up} searxng         http://localhost:8080     [green]healthy[/green]",
                    f"  {dot_dn} chroma          http://localhost:8000     [red]offline[/red]",
                    "",
                    "  [dim]Run [bold]/services start[/bold] to bring up missing services[/dim]",
                ]
            ),
            title="[cyan]Service Health[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "services_status")


# ── 7. GPU info ──────────────────────────────────────────────────────────


def capture_gpu():
    c = make_console()
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]GPU[/bold]  NVIDIA GeForce RTX 4070 Ti SUPER",
                    "[bold]VRAM[/bold] 16,384 MiB total  •  14,208 MiB free  •  2,176 MiB used",
                    "",
                    "[bold cyan]Recommended model:[/bold cyan]",
                    "  [green]+[/green]  [bold]qwen2.5-coder:14b[/bold]  (~10 GB)",
                    "",
                    "[bold cyan]VRAM tiers:[/bold cyan]",
                    "  [green]●[/green]  22+ GB    qwen2.5-coder:32b-instruct-q4_K_M",
                    "  [green]●[/green]  11+ GB    [bold]qwen2.5-coder:14b[/bold]  [dim]← current[/dim]",
                    "  [dim]●[/dim]  9.5+ GB   deepseek-r1:14b",
                    "  [dim]●[/dim]  5+ GB     llama3.1:8b",
                    "",
                    "[dim]Run [bold]/gpu use[/bold] to auto-switch to recommended model[/dim]",
                ]
            ),
            title="[cyan]GPU & VRAM[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "gpu_info")


# ── 8. Intent classification ─────────────────────────────────────────────


def capture_intent():
    c = make_console()
    c.print("[dim]> write a python function to sort a list[/dim]")
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]Intent:[/bold]    [bold green]code[/bold green]",
                    "[bold]Score:[/bold]     0.95",
                    "[bold]Layer:[/bold]     keyword (regex match)",
                    "[bold]Latency:[/bold]   0.2 ms",
                    "",
                    "[dim]Matched rule: write|implement|code|debug + function|class|code[/dim]",
                ]
            ),
            title="[cyan]Intent Classification[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    c.print()
    c.print("[dim]> hello how are you today[/dim]")
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]Intent:[/bold]    [bold green]chat[/bold green]",
                    "[bold]Score:[/bold]     0.82",
                    "[bold]Layer:[/bold]     embedding (ONNX cosine similarity)",
                    "[bold]Latency:[/bold]   12.4 ms",
                    "",
                    "[dim]No keyword match — fell through to embedding layer[/dim]",
                ]
            ),
            title="[cyan]Intent Classification[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "intent_classify")


# ── 9. SD status ─────────────────────────────────────────────────────────


def capture_sd_status():
    c = make_console()
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]Image[/bold]  AUTOMATIC1111  localhost:7860  [green]● running[/green]",
                    "[bold]Video[/bold]  ComfyUI        localhost:8188  [red]● stopped[/red]",
                    "",
                    "  GPU: 12,208 MiB free  •  ~4,176 MiB in use",
                    "  Mode: [bold]image[/bold]",
                    "",
                    "[dim]Commands:[/dim]",
                    "  [yellow]/sd video[/yellow]   switch to ComfyUI video mode",
                    "  [yellow]/sd stop[/yellow]    stop SD and reclaim VRAM for LLMs",
                    "  [yellow]/sd start[/yellow]   start last-active mode",
                ]
            ),
            title="[cyan]Stable Diffusion[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "sd_status")


# ── 10. Image generation ─────────────────────────────────────────────────


def capture_generate_image():
    c = make_console()
    c.print("[dim]> /generate image a sunset over mountains in watercolor style[/dim]")
    c.print()
    c.print("[cyan]Switching to [bold]llama3.1:8b[/bold] for prompt crafting...[/cyan]")
    c.print(
        "[cyan]Prompt: a breathtaking sunset over snow-capped mountains, "
        "watercolor painting style, soft washes of orange and purple, "
        "wet-on-wet technique, atmospheric perspective, muted earth tones, "
        "paper texture visible[/cyan]"
    )
    c.print()
    c.print("[yellow]Freeing GPU for stable-diffusion...[/yellow]")
    c.print(
        Panel(
            "VRAM: 2,176/16,384 MB used  (14,208 MB free)  --  NVIDIA GeForce RTX 4070 Ti SUPER",
            title="[cyan]GPU freed[/cyan]",
            border_style="dim",
            expand=False,
        )
    )
    c.print()
    c.print("[cyan]Generating...[/cyan] ████████████████████████████████████████ 100%  0:00:00")
    c.print()
    c.print("[green]Image saved:[/green] clod_20260311_143022_a8f2.png")
    c.print("[dim]Reload qwen2.5-coder:14b? [y/N][/dim]")
    save(c, "generate_image")


# ── 11. Model switch ─────────────────────────────────────────────────────


def capture_model_switch():
    c = make_console()
    c.print("[dim]> /model deepseek-r1:14b[/dim]")
    c.print("[cyan]Switching to [bold]deepseek-r1:14b[/bold] for reason...[/cyan]")
    c.print(
        Panel(
            "VRAM: 10,240/16,384 MB used  (6,144 MB free)  --  NVIDIA GeForce RTX 4070 Ti SUPER",
            title="[cyan]Unloading...[/cyan]",
            border_style="dim",
            expand=False,
        )
    )
    c.print(
        Panel(
            "VRAM: 512/16,384 MB used  (15,872 MB free)  --  NVIDIA GeForce RTX 4070 Ti SUPER",
            title="[cyan]Loading...[/cyan]",
            border_style="dim",
            expand=False,
        )
    )
    c.print(
        Panel(
            "VRAM: 9,216/16,384 MB used  (7,168 MB free)  --  NVIDIA GeForce RTX 4070 Ti SUPER",
            title="[cyan]Ready[/cyan]",
            border_style="dim",
            expand=False,
        )
    )
    c.print("[green]Model switched to deepseek-r1:14b[/green]")
    save(c, "model_switch")


# ── 12. Startup banner ──────────────────────────────────────────────────


def capture_startup():
    c = make_console()
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]CPU[/bold]  13th Gen Intel Core i7-13700K  [dim]16c / 24t[/dim]",
                    "[bold]RAM[/bold]  32,604 MiB total  •  18,432 MiB free",
                    "[bold]GPU[/bold]  NVIDIA GeForce RTX 4070 Ti SUPER  16,384 MiB total  •  14,208 MiB free",
                    "[bold]MCP[/bold]  [green]running[/green]  localhost:8765  [dim]D:\\projects[/dim]",
                    "[bold]Services[/bold]  [green]●[/green] ollama  [green]●[/green] litellm  [green]●[/green] pipelines  [green]●[/green] searxng  [green]●[/green] chroma",
                    "",
                    "[bold cyan]Recommendation[/bold cyan]",
                    "  [green]+[/green]  [bold]qwen2.5-coder:14b[/bold]",
                ]
            ),
            title="[cyan]System[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "startup_banner")


# ── 13. Services start / docker startup ──────────────────────────────────


def capture_services_start():
    c = make_console()
    c.print(
        Panel(
            "\n".join(
                [
                    "The following services are not running:",
                    "  [red]●[/red] [bold]ollama[/bold]  [dim](local LLM inference)[/dim]",
                    "  [red]●[/red] [bold]litellm[/bold]  [dim](cloud model gateway)[/dim]",
                    "  [red]●[/red] [bold]pipelines[/bold]  [dim](two-stage routing)[/dim]",
                    "  [red]●[/red] [bold]searxng[/bold]  [dim](web search)[/dim]",
                    "  [red]●[/red] [bold]chroma[/bold]  [dim](vector memory)[/dim]",
                    "",
                    "[dim]Run [bold]docker compose up -d[/bold] to start them?[/dim]",
                ]
            ),
            title="[yellow]Services Offline[/yellow]",
            border_style="yellow",
            expand=False,
        )
    )
    c.print("[yellow]Start core docker services now? (y/n)[/yellow] y")
    c.print("[dim]Running docker compose up -d (this may take a few minutes on first run)...[/dim]")
    c.print("[dim]Waiting for services to come up...[/dim]")
    c.print("[green]All services started successfully.[/green]")
    save(c, "services_start")


# ── 14. Tool call example ────────────────────────────────────────────────


def capture_tool_call():
    c = make_console()
    c.print("[dim]> list all python files in the current directory[/dim]")
    c.print()
    c.print(
        Panel(
            '[bold]bash_exec[/bold]\n[dim]{\n  "command": "find . -name \'*.py\' -type f | head -20",\n  "timeout": 30\n}[/dim]',
            title="[yellow]tool call[/yellow]",
            border_style="yellow",
        )
    )
    c.print("[yellow]Execute this command? [y/N][/yellow] y")
    c.print(
        Panel(
            "[dim]./clod.py\n./intent.py\n./mcp_server.py\n./pipelines/code_review_pipe.py\n"
            "./pipelines/reason_review_pipe.py\n./pipelines/chat_assist_pipe.py\n"
            "./pipelines/claude_review_pipe.py\n./tests/conftest.py[/dim]",
            title="[green]result: bash_exec[/green]",
            border_style="green",
        )
    )
    c.print()
    c.print("Found 8 Python files in the current directory:")
    c.print("- [bold]clod.py[/bold] — Main CLI application")
    c.print("- [bold]intent.py[/bold] — Intent classification engine")
    c.print("- [bold]mcp_server.py[/bold] — MCP filesystem server")
    c.print("- [bold]pipelines/[/bold] — 4 pipeline definitions")
    c.print("- [bold]tests/conftest.py[/bold] — Test configuration")
    save(c, "tool_call")


# ── 15. Token budget ─────────────────────────────────────────────────────


def capture_tokens():
    c = make_console()
    c.print("[dim]> /tokens[/dim]")
    c.print(
        Panel(
            "\n".join(
                [
                    "[bold]Claude Token Budget[/bold]",
                    "",
                    "  Used:      [yellow]45,200[/yellow] / 100,000",
                    "  Remaining: 54,800",
                    "  Progress:  [yellow]████████████████████░░░░░░░░░░░░░░░░░░░░[/yellow] 45%",
                    "",
                    "[dim]Budget resets each session. Configure in %APPDATA%\\clod\\config.json[/dim]",
                ]
            ),
            title="[cyan]Token Budget[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    save(c, "tokens")


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Capturing screenshots as SVG...")
    capture_help()
    capture_header_default()
    capture_header_pipeline()
    capture_header_tokens()
    capture_header_offline()
    capture_services()
    capture_gpu()
    capture_intent()
    capture_sd_status()
    capture_generate_image()
    capture_model_switch()
    capture_startup()
    capture_services_start()
    capture_tool_call()
    capture_tokens()
    print(f"\nDone! {15} SVGs saved to assets/")
