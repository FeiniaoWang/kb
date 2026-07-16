from kb.core.housekeeping import InitFailure, InitResult


def render_init_text(result: InitResult) -> str:
    lines = [f"created  {path}" for path in result.created]
    lines.extend(f"overwritten  {path}" for path in result.overwritten)
    lines.extend(f"skipped  {path} (exists)" for path in result.skipped)
    lines.sort(key=lambda line: line.split("  ", 1)[1].removesuffix(" (exists)"))
    lines.append(
        f"KB ready at {result.root} — {len(result.created)} created, "
        f"{len(result.overwritten)} overwritten, {len(result.skipped)} skipped"
    )
    return "\n".join(lines)


def render_error_text(error: InitFailure) -> str:
    return f"{error.code}: {error.message}"
