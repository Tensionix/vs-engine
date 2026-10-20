"""The reference part of the documents, made from the map of the program (core\\program_map.py): `vs_cli.cmd map --docs`.

Nothing here is written from memory of the code: the sections and their presets come from the layout of the window, the
operations, fields and choices with their tooltips from the manifest - so the window, the console command and the
documents say one thing.

    docs\\OPERATIONS_RU.md, _EN.md   section -> preset -> its fields, the call of the console command; the fields every
                                    preset has; SETUP; SERVICE
    blocks of written documents     a table between <!-- map:NAME --> and <!-- /map -->; the text around them is the
                                    person's. NAME: sections, presets, machine, setup, service, encoders

A document is written only when its text changed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .program_map import as_text

MACHINE_SECTIONS = ("processing", "encoding", "run")
GENERATED = {
    "en": "Made from the data of the program by `vs_cli.cmd map --docs`: the manifest of the operations "
          "(`config\\tool_manifest.yaml`) and the layout of the window (`config\\window_layout.yaml`). It is not edited by "
          "hand: a text is changed there and the command is run again.",
    "ru": "Собрано из данных программы командой `vs_cli.cmd map --docs`: манифест операций (`config\\tool_manifest.yaml`) "
          "и раскладка окна (`config\\window_layout.yaml`). Руками не правится: текст меняется там, и команда запускается снова.",
}
WORDS = {
    "en": {"title": "Operations", "presets": "Presets", "field": "Field", "kind": "Kind", "default": "Default", "choices": "Choices",
           "about": "What it is", "call": "Call", "machine": "Every preset and profile: processing, encoding, run",
           "machine_note": "These fields stand on every page: the processing and the cards of the encoder are one for the "
                           "whole window, set on one page they are set on all.",
           "setup": "SETUP: the additional components", "service": "SERVICE: checks", "details": "SOURCE INFO", "buttons": "Buttons of a page",
           "encoders": "Encoders", "encoder": "Encoder", "cards": "Cards", "operation": "Operation",
           "where": "Where the result goes", "where_text": "`<Target>\\<Palette>\\<preset>_<encoder>\\<the folders of the "
                    "Source>\\<name>.<ext>`; a profile - `<Target>\\Profiles\\<profile>_<encoder>\\...`. The name of the "
                    "source is kept. A result that is there is passed over unless *Overwrite*.",
           "from": "from", "range": "{low} … {high}, step {step}",
           "section": "Section", "group": "Group", "preset": "Preset", "mlrt": "on vs-mlrt: shown with an NVIDIA RTX card or MLRT"},
    "ru": {"title": "Операции", "presets": "Пресеты", "field": "Поле", "kind": "Вид", "default": "По умолчанию", "choices": "Варианты",
           "about": "Что это", "call": "Вызов", "machine": "У каждого пресета и профиля: обработка, кодирование, прогон",
           "machine_note": "Эти поля стоят на каждой странице: обработка и карточки кодера одни на всё окно - заданные на "
                           "одной странице, они заданы на всех.",
           "setup": "SETUP: дополнительные компоненты", "service": "СЕРВИС: проверки", "details": "СВЕДЕНИЯ", "buttons": "Кнопки страницы",
           "encoders": "Кодеры", "encoder": "Кодер", "cards": "Карточки", "operation": "Операция",
           "where": "Куда ложится результат", "where_text": "`<Назначение>\\<Палитра>\\<пресет>_<кодер>\\<папки "
                    "Источника>\\<имя>.<расш>`; профиль - `<Назначение>\\Profiles\\<профиль>_<кодер>\\...`. Имя исходника "
                    "сохраняется. Готовый результат пропускается, если не включено *Перезаписать*.",
           "from": "из", "range": "{low} … {high}, шаг {step}",
           "section": "Раздел", "group": "Группа", "preset": "Пресет", "mlrt": "на vs-mlrt: виден при видеокарте NVIDIA RTX или MLRT"},
}
KINDS = {
    "en": {"radio": "choice", "checkbox": "tick", "number": "number", "text": "text"},
    "ru": {"radio": "выбор", "checkbox": "флажок", "number": "число", "text": "текст"},
}


def _t(item: dict[str, Any], key: str, language: str) -> str:
    return str(item.get(f"{key}_ru") or item.get(key) or "") if language == "ru" else str(item.get(key) or "")


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _choices(field: dict[str, Any], language: str) -> str:
    words = WORDS[language]
    if field.get("choices_from"):
        return f"{words['from']} `{field['choices_from'].rsplit(':', 1)[-1]}`"
    if field.get("choices"):
        return ", ".join(f"`{choice['value']}` {_t(choice, 'label', language)}".strip() for choice in field["choices"])
    if field["kind"] == "number":
        return words["range"].format(low=field.get("min"), high=field.get("max"), step=field.get("step"))
    return ""


def _fields_table(fields: list[dict[str, Any]], language: str) -> list[str]:
    words = WORDS[language]
    lines = [f"| {words['field']} | {words['kind']} | {words['default']} | {words['choices']} | {words['about']} |",
             "|---|---|---|---|---|"]
    for field in fields:
        about = _t(field, "tooltip", language)
        when = _t(field, "when", language)
        lines.append(f"| `{field['id']}` {_cell(_t(field, 'label', language))} | {KINDS[language].get(field['kind'], field['kind'])} | "
                     f"`{_cell(as_text(field['default']))}` | {_cell(_choices(field, language))} | "
                     f"{_cell(about + (f' ({when})' if when else ''))} |")
    return lines


def block_sections(told: dict[str, Any], language: str) -> list[str]:
    """Every preset where the window stands it - its palette, its group, its name - and the call that does the same."""
    words = WORDS[language]
    lines = [f"| {words['section']} | {words['group']} | {words['preset']} | {words['call']} |", "|---|---|---|---|"]
    for section in told["sections"]:
        groups = {group["id"]: _t(group, "title", language) for group in section.get("groups") or []}
        for mode in section["modes"]:
            node = told["operations"][mode["op"]]
            mark = " ¹" if node.get("needs") == "mlrt" else ""
            lines.append(f"| {_cell(_t(section, 'title', language))} | {_cell(groups.get(mode.get('group', ''), ''))} | "
                         f"{_cell(_t(node, 'title', language))}{mark} | `{node['call']}` |")
    if any(node.get("needs") == "mlrt" for node in told["operations"].values()):
        lines += ["", f"¹ {words['mlrt']}."]
    return lines + [""]


def block_presets(told: dict[str, Any], language: str) -> list[str]:
    words, lines = WORDS[language], []
    for section in told["sections"]:
        lines += [f"### {_t(section, 'title', language)}", "", _t(section, "about", language), ""]
        for mode in section["modes"]:
            node = told["operations"][mode["op"]]
            own = [field for field in node["fields"] if field["section"] not in MACHINE_SECTIONS]
            lines += [f"#### {_t(node, 'title', language)} (`{node['id']}`)", "",
                      f"*{_t(node, 'about', language)}*. {_t(node, 'description', language)}".strip(), "",
                      f"{words['call']}: `{node['call']}`", ""]
            if own:
                lines += _fields_table(own, language) + [""]
    return lines


def block_machine(told: dict[str, Any], language: str) -> list[str]:
    words = WORDS[language]
    first = next(node for node in told["operations"].values() if node["service"] == "run_preset")
    fields = [field for field in first["fields"] if field["section"] in MACHINE_SECTIONS]
    return [words["machine_note"], ""] + _fields_table(fields, language) + ["", f"**{words['where']}.** {words['where_text']}", ""]


def _operations_table(told: dict[str, Any], names: list[str], language: str) -> list[str]:
    words = WORDS[language]
    lines = [f"| {words['operation']} | {words['about']} | {words['call']} |", "|---|---|---|"]
    for name in names:
        node = told["operations"][name]
        lines.append(f"| {_cell(_t(node, 'title', language))} | {_cell(_t(node, 'description', language))} | `{node['call']}` |")
    return lines + [""]


def block_setup(told: dict[str, Any], language: str) -> list[str]:
    """SETUP of the header: what the program needs to work."""
    return _operations_table(told, told["setup"], language)


def block_service(told: dict[str, Any], language: str) -> list[str]:
    """SERVICE of the header, DETAILS of the work zone and the buttons of a page."""
    return _operations_table(told, [*told["service"], *told["details"], *[button["op"] for button in told["buttons"]]], language)


def block_encoders(told: dict[str, Any], language: str) -> list[str]:
    from system_core.engine import encoding

    words = WORDS[language]
    lines = [f"| {words['encoder']} | {words['cards']} |", "|---|---|"]
    for name in told["encoders"]:
        cards = encoding.cards_of(name)
        shown = {key: value for key, value in cards.items()
                 if key == "encode_family" or cards["encode_family"] in encoding.SHOWN.get(key, ())}
        lines.append(f"| `{name}` | " + ", ".join(f"`{key}={value}`" for key, value in shown.items()) + " |")
    return lines + [""]


BLOCKS = {"sections": block_sections, "presets": block_presets, "machine": block_machine, "setup": block_setup,
          "service": block_service, "encoders": block_encoders}


def operations_document(told: dict[str, Any], language: str) -> str:
    words = WORDS[language]
    name = told["tool"].get("name") or "Audion VS Engine"
    lines = [f"# {name} — {words['title']}", "", f"> {GENERATED[language]}", "",
             f"## {words['presets']}", "", *block_presets(told, language),
             f"## {words['machine']}", "", *block_machine(told, language),
             f"## {words['setup']}", "", *block_setup(told, language),
             f"## {words['service']}", "", *block_service(told, language),
             f"## {words['encoders']}", "", *block_encoders(told, language)]
    return "\n".join(lines).rstrip() + "\n"


MARK = re.compile(r"(<!-- map:(?P<name>[a-z_]+) -->\n)(?P<body>.*?)(<!-- /map -->)", re.DOTALL)


def _language_of(path: Path) -> str:
    return "ru" if path.stem.upper().endswith("_RU") else "en"


def _fill_blocks(text: str, told: dict[str, Any], language: str) -> str:
    def replace(found: re.Match[str]) -> str:
        block = BLOCKS.get(found["name"])
        if block is None:
            return found.group(0)
        return found.group(1) + "\n".join(block(told, language)).rstrip() + "\n" + found.group(4)

    return MARK.sub(replace, text)


def write(told: dict[str, Any], root: Path) -> list[Path]:
    """The documents whose text changed, written; the list of them."""
    root = Path(root)
    written: list[Path] = []

    def put(path: Path, text: str) -> None:
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(path)

    for language in ("en", "ru"):
        put(root / "docs" / f"OPERATIONS_{language.upper()}.md", operations_document(told, language))
    for path in sorted([*root.glob("*.md"), *(root / "docs").glob("*.md")]):
        if path.name.startswith("OPERATIONS_"):
            continue
        text = path.read_text(encoding="utf-8")
        if "<!-- map:" in text:
            put(path, _fill_blocks(text, told, _language_of(path)))
    return written
