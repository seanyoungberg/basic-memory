"""CLI tool commands for Basic Memory.

Every command calls its MCP tool with output_format="json" and prints the result.
No text formatting, no separate code paths, no duplicate data fetching.
"""

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

import typer
from loguru import logger

from basic_memory.cli.app import app
from basic_memory.cli.commands.command_utils import run_with_cleanup
from basic_memory.cli.commands.routing import force_routing, validate_routing_flags
from basic_memory.mcp.tools import build_context as mcp_build_context
from basic_memory.mcp.tools import edit_note as mcp_edit_note
from basic_memory.mcp.tools import list_memory_projects as mcp_list_projects
from basic_memory.mcp.tools import list_workspaces as mcp_list_workspaces
from basic_memory.mcp.tools import move_note as mcp_move_note
from basic_memory.mcp.tools import read_note as mcp_read_note
from basic_memory.mcp.tools import recent_activity as mcp_recent_activity
from basic_memory.mcp.tools import schema_diff as mcp_schema_diff
from basic_memory.mcp.tools import schema_infer as mcp_schema_infer
from basic_memory.mcp.tools import schema_validate as mcp_schema_validate
from basic_memory.mcp.tools import search_notes as mcp_search
from basic_memory.mcp.tools import write_note as mcp_write_note

tool_app = typer.Typer()
app.add_typer(tool_app, name="tool", help="Access to MCP tools via CLI")

VALID_EDIT_OPERATIONS = ["append", "prepend", "find_replace", "replace_section"]


# --- Shared helpers ---


def _print_json(result: Any) -> None:
    """Print a result as formatted JSON."""
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))


# --- Commands ---


@tool_app.command()
def write_note(
    title: Annotated[str, typer.Option(help="The title of the note")],
    folder: Annotated[str, typer.Option(help="The folder to create the note in")],
    content: Annotated[
        Optional[str],
        typer.Option(
            help="The content of the note. If not provided, content will be read from stdin."
        ),
    ] = None,
    tags: Annotated[
        Optional[List[str]], typer.Option(help="A list of tags to apply to the note")
    ] = None,
    project: Annotated[
        Optional[str],
        typer.Option(
            help="The project to write to. If not provided, the default project will be used."
        ),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Create or update a markdown note. Content can be provided via --content or stdin.

    Examples:

    bm tool write-note --title "My Note" --folder "notes" --content "Note content"
    echo "content" | bm tool write-note --title "My Note" --folder "notes"
    bm tool write-note --title "My Note" --folder "notes" --local
    """
    try:
        validate_routing_flags(local, cloud)

        # If content is not provided, read from stdin
        if content is None:
            if not sys.stdin.isatty():
                content = sys.stdin.read()
            else:  # pragma: no cover
                typer.echo(
                    "No content provided. Please provide content via --content or by piping to stdin.",
                    err=True,
                )
                raise typer.Exit(1)

        if content is not None and not content.strip():
            typer.echo("Empty content provided. Please provide non-empty content.", err=True)
            raise typer.Exit(1)

        assert content is not None

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_write_note(
                    title=title,
                    content=content,
                    directory=folder,
                    project=project,
                    project_id=project_id,
                    tags=tags,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during write_note: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command()
def read_note(
    identifier: str,
    include_frontmatter: bool = typer.Option(
        False, "--include-frontmatter", help="Include YAML frontmatter in output"
    ),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Read a markdown note from the knowledge base.

    Examples:

    bm tool read-note my-note
    bm tool read-note my-note --include-frontmatter
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_read_note(
                    identifier=identifier,
                    project=project,
                    project_id=project_id,
                    include_frontmatter=include_frontmatter,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during read_note: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command()
def edit_note(
    identifier: str,
    operation: Annotated[str, typer.Option("--operation", help="Edit operation to apply")],
    content: Annotated[str, typer.Option("--content", help="Content for the edit operation")],
    find_text: Annotated[
        Optional[str], typer.Option("--find-text", help="Text to find for find_replace operation")
    ] = None,
    section: Annotated[
        Optional[str],
        typer.Option("--section", help="Section heading for replace_section operation"),
    ] = None,
    expected_replacements: int = typer.Option(
        1,
        "--expected-replacements",
        help="Expected replacement count for find_replace operation",
    ),
    project: Annotated[
        Optional[str],
        typer.Option(
            help="The project to edit. If not provided, the default project will be used."
        ),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Edit an existing markdown note using append/prepend/find_replace/replace_section.

    Examples:

    bm tool edit-note my-note --operation append --content "new content"
    bm tool edit-note my-note --operation find_replace --find-text "old" --content "new"
    bm tool edit-note my-note --operation replace_section --section "## Notes" --content "updated"
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_edit_note(
                    identifier=identifier,
                    operation=operation,
                    content=content,
                    project=project,
                    project_id=project_id,
                    section=section,
                    find_text=find_text,
                    expected_replacements=expected_replacements,
                    output_format="json",
                )
            )

        # MCP tool returns error field on failure in JSON mode
        if isinstance(result, dict) and result.get("error"):
            typer.echo(f"Error: {result['error']}", err=True)
            raise typer.Exit(1)

        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during edit_note: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command("move-note")
def move_note(
    identifier: Annotated[
        str,
        typer.Argument(help="Exact note identifier (title, permalink, or memory:// URL)"),
    ],
    destination_path: Annotated[
        Optional[str],
        typer.Argument(
            help="New path relative to project root (e.g., archive/2026/old-note.md). "
            "Mutually exclusive with --destination-folder."
        ),
    ] = None,
    destination_folder: Annotated[
        Optional[str],
        typer.Option(
            "--destination-folder",
            help="Move into this folder, preserving the original filename. "
            "Mutually exclusive with the destination_path positional argument.",
        ),
    ] = None,
    is_directory: bool = typer.Option(
        False,
        "--directory",
        help="Treat identifier as a directory path and move the entire subtree.",
    ),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Move a note (or directory) to a new location, updating DB and search index.

    Thin wrapper around the move_note MCP tool. Use this when you want the
    database, search index, and permalink to update atomically — `git mv`
    requires a separate `bm reindex` to re-sync.

    Examples:

    bm tool move-note "My Note" archive/2026/my-note.md
    bm tool move-note my-note-permalink --destination-folder archive
    bm tool move-note docs/old-tree archive/docs --directory
    """
    try:
        validate_routing_flags(local, cloud)

        if destination_path and destination_folder:
            typer.echo(
                "Error: provide either a destination path argument or --destination-folder, not both.",
                err=True,
            )
            raise typer.Exit(1)
        if not destination_path and not destination_folder:
            typer.echo(
                "Error: provide either a destination path argument or --destination-folder.",
                err=True,
            )
            raise typer.Exit(1)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_move_note(
                    identifier=identifier,
                    destination_path=destination_path or "",
                    destination_folder=destination_folder,
                    is_directory=is_directory,
                    project=project,
                    project_id=project_id,
                    output_format="json",
                )
            )

        # MCP move_note returns a dict in JSON mode with `moved: bool` and an
        # optional `error` field. Surface non-zero exit on failure so scripts
        # can branch reliably.
        if isinstance(result, dict) and result.get("error"):
            _print_json(result)
            raise typer.Exit(1)
        if isinstance(result, dict) and result.get("moved") is False:
            _print_json(result)
            raise typer.Exit(1)

        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during move_note: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command()
def build_context(
    url: str,
    depth: Optional[int] = typer.Option(1, "--depth", help="Depth of context to build"),
    timeframe: Optional[str] = typer.Option(
        "7d", "--timeframe", help="Timeframe filter (e.g., '7d', '1 week')"
    ),
    page: int = typer.Option(1, "--page", help="Page number for pagination"),
    page_size: int = typer.Option(10, "--page-size", help="Number of results per page"),
    max_related: int = typer.Option(10, "--max-related", help="Maximum related items to return"),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Get context needed to continue a discussion.

    Examples:

    bm tool build-context memory://specs/search
    bm tool build-context specs/search --depth 2 --timeframe 30d
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_build_context(
                    url=url,
                    project=project,
                    project_id=project_id,
                    depth=depth,
                    timeframe=timeframe,
                    page=page,
                    page_size=page_size,
                    max_related=max_related,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during build_context: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command()
def recent_activity(
    type: Annotated[Optional[List[str]], typer.Option(help="Filter by item type")] = None,
    depth: Optional[int] = typer.Option(1, "--depth", help="Depth of context to build"),
    timeframe: Optional[str] = typer.Option(
        "7d", "--timeframe", help="Timeframe filter (e.g., '7d', '1 week')"
    ),
    page: int = typer.Option(1, "--page", help="Page number for pagination"),
    page_size: int = typer.Option(50, "--page-size", help="Number of results per page"),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Get recent activity across the knowledge base.

    Examples:

    bm tool recent-activity
    bm tool recent-activity --timeframe 30d --page-size 20
    bm tool recent-activity --type entity --type observation
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_recent_activity(
                    type=type or "",
                    depth=depth if depth is not None else 1,
                    timeframe=timeframe if timeframe is not None else "7d",
                    page=page,
                    page_size=page_size,
                    project=project,
                    project_id=project_id,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during recent_activity: {e}", err=True)
            raise typer.Exit(1)
        raise


@tool_app.command("search-notes")
def search_notes(
    query: Annotated[
        Optional[str],
        typer.Argument(help="Search query string (optional when using metadata filters)"),
    ] = "",
    permalink: Annotated[bool, typer.Option("--permalink", help="Search permalink values")] = False,
    title: Annotated[bool, typer.Option("--title", help="Search title values")] = False,
    vector: Annotated[bool, typer.Option("--vector", help="Use vector retrieval")] = False,
    hybrid: Annotated[bool, typer.Option("--hybrid", help="Use hybrid retrieval")] = False,
    after_date: Annotated[
        Optional[str],
        typer.Option("--after_date", help="Search results after date, eg. '2d', '1 week'"),
    ] = None,
    tags: Annotated[
        Optional[List[str]],
        typer.Option("--tag", help="Filter by frontmatter tag (repeatable)"),
    ] = None,
    status: Annotated[
        Optional[str],
        typer.Option("--status", help="Filter by frontmatter status"),
    ] = None,
    note_types: Annotated[
        Optional[List[str]],
        typer.Option("--type", help="Filter by frontmatter type (repeatable)"),
    ] = None,
    entity_types: Annotated[
        Optional[List[str]],
        typer.Option(
            "--entity-type",
            help="Filter by search item type: entity, observation, relation (repeatable)",
        ),
    ] = None,
    meta: Annotated[
        Optional[List[str]],
        typer.Option("--meta", help="Filter by frontmatter key=value (repeatable)"),
    ] = None,
    filter_json: Annotated[
        Optional[str],
        typer.Option("--filter", help="JSON metadata filter (advanced)"),
    ] = None,
    page: int = typer.Option(1, "--page", help="Page number for pagination"),
    page_size: int = typer.Option(10, "--page-size", help="Number of results per page"),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Search across all content in the knowledge base.

    Examples:

    bm tool search-notes "my query"
    bm tool search-notes --permalink "specs/*"
    bm tool search-notes --tag python --tag async
    bm tool search-notes --meta status=draft
    """
    try:
        validate_routing_flags(local, cloud)

        mode_flags = [permalink, title, vector, hybrid]
        if sum(1 for enabled in mode_flags if enabled) > 1:  # pragma: no cover
            typer.echo(
                "Use only one mode flag: --permalink, --title, --vector, or --hybrid. Exiting.",
                err=True,
            )
            raise typer.Exit(1)

        # --- Build metadata filters from --filter and --meta ---
        metadata_filters: Dict[str, Any] | None = {}
        if filter_json:
            try:
                metadata_filters = json.loads(filter_json)
                if not isinstance(metadata_filters, dict):
                    raise ValueError("Metadata filter JSON must be an object")
            except json.JSONDecodeError as e:
                typer.echo(f"Invalid JSON for --filter: {e}", err=True)
                raise typer.Exit(1)

        if meta:
            for item in meta:
                if "=" not in item:
                    typer.echo(
                        f"Invalid --meta entry '{item}'. Use key=value format.",
                        err=True,
                    )
                    raise typer.Exit(1)
                key, value = item.split("=", 1)
                key = key.strip()
                if not key:
                    typer.echo(f"Invalid --meta entry '{item}'.", err=True)
                    raise typer.Exit(1)
                metadata_filters[key] = value

        if not metadata_filters:
            metadata_filters = None

        # --- Determine search type from mode flags ---
        search_type: str | None = None
        if permalink:
            search_type = "permalink"
        if title:
            search_type = "title"
        if vector:
            search_type = "vector"
        if hybrid:
            search_type = "hybrid"

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_search(
                    query=query or None,
                    project=project,
                    project_id=project_id,
                    search_type=search_type,
                    output_format="json",
                    page=page,
                    after_date=after_date,
                    page_size=page_size,
                    note_types=note_types,
                    entity_types=entity_types,
                    metadata_filters=metadata_filters,
                    tags=tags,
                    status=status,
                )
            )

        # MCP tool may return a string error message
        if isinstance(result, str):
            typer.echo(result, err=True)
            raise typer.Exit(1)

        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            logger.exception("Error during search", e)
            typer.echo(f"Error during search: {e}", err=True)
            raise typer.Exit(1)
        raise


# --- list-projects ---


@tool_app.command("list-projects")
def list_projects(
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """List all available projects with their status (JSON output).

    Examples:

    bm tool list-projects
    bm tool list-projects --local
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(mcp_list_projects(output_format="json"))
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during list_projects: {e}", err=True)
            raise typer.Exit(1)
        raise


# --- list-workspaces ---


@tool_app.command("list-workspaces")
def list_workspaces(
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """List available cloud workspaces (JSON output).

    Examples:

    bm tool list-workspaces
    bm tool list-workspaces --cloud
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(mcp_list_workspaces(output_format="json"))
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during list_workspaces: {e}", err=True)
            raise typer.Exit(1)
        raise


# --- schema-validate ---


@tool_app.command("schema-validate")
def schema_validate(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Note path, note type, or directory of notes to validate"),
    ] = None,
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        "-r",
        help="When TARGET is a directory, walk subdirectories (default: on)",
    ),
):
    """Validate notes against their schemas (JSON output).

    TARGET can be:
      - a note type (e.g., person) — validates all notes of that type
      - a note path (e.g., people/ada-lovelace.md) — validates a single note
      - a directory (e.g., domains/foo/) — validates every .md file under it

    Directory mode aggregates per-file ValidationReports into a single report
    so the JSON shape stays consistent with single-note / by-type validation.

    Examples:

    bm tool schema-validate person
    bm tool schema-validate people/ada-lovelace.md
    bm tool schema-validate domains/foo/
    bm tool schema-validate domains/foo/ --no-recursive
    """
    try:
        validate_routing_flags(local, cloud)

        # Directory mode: walk .md files and aggregate per-file reports.
        # The MCP layer's identifier path is single-note (link_resolver.resolve_link),
        # so passing a directory used to fuzzy-match exactly one arbitrary note —
        # silently ignoring everything else under the tree.
        target_path = Path(target) if target else None
        if target_path and target_path.is_dir():
            with force_routing(local=local, cloud=cloud):
                aggregated = _validate_directory(
                    target_path,
                    recursive=recursive,
                    project=project,
                )
            _print_json(aggregated)
            return

        # Heuristic: if target contains / or ., treat as identifier; otherwise as note type
        note_type, identifier = None, None
        if target:
            if "/" in target or "." in target:
                identifier = target
            else:
                note_type = target

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_schema_validate(
                    note_type=note_type,
                    identifier=identifier,
                    project=project,
                    project_id=project_id,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during schema_validate: {e}", err=True)
            raise typer.Exit(1)
        raise


def _validate_directory(
    directory: Path,
    *,
    recursive: bool,
    project: Optional[str],
) -> Dict[str, Any]:
    """Walk a directory of .md files, validate each, aggregate the reports."""
    pattern = "**/*.md" if recursive else "*.md"
    files = sorted(p for p in directory.glob(pattern) if p.is_file())

    aggregated_results: List[Any] = []
    total_entities = 0
    skipped: List[str] = []

    for f in files:
        # The MCP layer accepts vault-relative paths via its link resolver, which
        # tries permalink → title → file path. Pass the path as-given (user's CWD)
        # which mirrors how the existing single-file path heuristic works today.
        identifier = str(f)
        try:
            result = run_with_cleanup(
                mcp_schema_validate(
                    note_type=None,
                    identifier=identifier,
                    project=project,
                    output_format="json",
                )
            )
        except Exception as e:  # pragma: no cover
            skipped.append(f"{identifier}: {e}")
            continue

        if isinstance(result, dict) and "error" in result:
            skipped.append(f"{identifier}: {result['error']}")
            continue

        if not isinstance(result, dict):
            skipped.append(f"{identifier}: unexpected result shape")
            continue

        total_entities += int(result.get("total_entities", 0))
        for r in result.get("results", []) or []:
            aggregated_results.append(r)

    valid_count = sum(1 for r in aggregated_results if r.get("passed"))
    warning_count = sum(len(r.get("warnings") or []) for r in aggregated_results)
    error_count = sum(len(r.get("errors") or []) for r in aggregated_results)

    return {
        "note_type": None,
        "directory": str(directory),
        "recursive": recursive,
        "files_walked": len(files),
        "total_entities": total_entities,
        "total_notes": len(aggregated_results),
        "valid_count": valid_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "skipped": skipped,
        "results": aggregated_results,
    }


# --- schema-infer ---


@tool_app.command("schema-infer")
def schema_infer(
    note_type: Annotated[
        str,
        typer.Argument(help="Note type to analyze (e.g., person, meeting)"),
    ],
    threshold: float = typer.Option(
        0.25, "--threshold", help="Minimum frequency for optional fields (0-1)"
    ),
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Infer schema from existing notes of a type (JSON output).

    Examples:

    bm tool schema-infer person
    bm tool schema-infer meeting --threshold 0.5
    bm tool schema-infer person --project research
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_schema_infer(
                    note_type=note_type,
                    threshold=threshold,
                    project=project,
                    project_id=project_id,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during schema_infer: {e}", err=True)
            raise typer.Exit(1)
        raise


# --- schema-diff ---


@tool_app.command("schema-diff")
def schema_diff(
    note_type: Annotated[
        str,
        typer.Argument(help="Note type to check for drift"),
    ],
    project: Annotated[
        Optional[str],
        typer.Option(help="The project to use. If not provided, the default project will be used."),
    ] = None,
    project_id: Annotated[
        Optional[str],
        typer.Option(
            "--project-id",
            help="Project external_id (UUID). Takes precedence over --project; use to disambiguate same-named projects across cloud workspaces.",
        ),
    ] = None,
    local: bool = typer.Option(
        False, "--local", help="Force local API routing (ignore cloud mode)"
    ),
    cloud: bool = typer.Option(False, "--cloud", help="Force cloud API routing"),
):
    """Show drift between schema and actual usage (JSON output).

    Examples:

    bm tool schema-diff person
    bm tool schema-diff person --project research
    """
    try:
        validate_routing_flags(local, cloud)

        with force_routing(local=local, cloud=cloud):
            result = run_with_cleanup(
                mcp_schema_diff(
                    note_type=note_type,
                    project=project,
                    project_id=project_id,
                    output_format="json",
                )
            )
        _print_json(result)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover
        if not isinstance(e, typer.Exit):
            typer.echo(f"Error during schema_diff: {e}", err=True)
            raise typer.Exit(1)
        raise
