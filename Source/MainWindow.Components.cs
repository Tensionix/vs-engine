using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Layout;
using Avalonia.Media;
using AudionVSEngine.Core;
using AudionVSEngine.Views;

namespace AudionVSEngine;

/// <summary>
/// The engine in the middle of the header: VapourSynth by its R-number, the plugins of install\vs_plugins.json the core
/// loads (N of M), FFmpeg, the driver of the video card. A badge each, a dot of freshness - Burn Orange when a newer
/// VapourSynth is out or a plugin does not load, forest green otherwise - the mark of the brand and the version. FFmpeg
/// and the driver are green always: the build of FFmpeg follows the NVIDIA driver, the driver is the user's. The console
/// command answers (vs_cli.cmd components), off the window's thread, once the window is up; GitHub at most once a day.
/// </summary>
public partial class MainWindow
{
    JsonElement? _components;

    async Task LoadComponents(bool refresh = false)
    {
        var told = await Door.Components(refresh);
        if (told is null) return;
        _components = told;
        ShowComponents();
        ShowSetupMark();
        ShowEngine();
        if (_sheet == "setup") FillSheet();
        // The first reading of a start: what is not installed is asked about (MainWindow.Setup.cs).
        if (!_setupAsked) await AskSetupAtStart();
    }

    /// <summary>What installs or updates a part of the engine: an operation of SERVICE.</summary>
    static readonly Dictionary<string, string> Installers = new()
    {
        ["vapoursynth"] = "install_vapoursynth", ["plugins"] = "install_vs_plugins", ["ffmpeg"] = "install_ffmpeg",
        ["mlrt"] = "install_mlrt",
    };

    IEnumerable<JsonElement> ComponentList() =>
        _components is { } told && told.TryGetProperty("components", out var list) ? list.EnumerateArray() : Enumerable.Empty<JsonElement>();

    /// <summary>The mark a part is drawn with: FFmpeg by its own; a GPU, the one of its maker; VapourSynth and the plugins have none.</summary>
    static string MarkOf(string id, string brand = "") => id switch { "gpu" => brand, _ => id };

    /// <summary>The name of a part in the language of the window: the console command names them in English.</summary>
    static string NameOf(string id, string name) => id == "plugins" ? Lang.T("Плагины") : name;

    static string Text(JsonElement component, string name) =>
        component.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";

    /// <summary>
    /// SETUP, COMPONENTS: every part of the engine with its version, the newest release, its state in the colour of the
    /// header, and the operation of SETUP that installs or updates it - its run goes to the journal as any other; INSTALL
    /// ALL installs the parts not yet in place one after another.
    /// </summary>
    void ComponentsCard(Panel column)
    {
        Open(column, "КОМПОНЕНТЫ");
        if (_components is null) { Note("Версии ещё читаются…"); return; }
        foreach (var component in ComponentList())
        {
            var id = Text(component, "id");
            if (id == "gpu") continue;
            string version = Text(component, "version"), latest = Text(component, "latest"), state = Text(component, "state");
            var row = new Grid { ColumnDefinitions = new ColumnDefinitions("22,96,110,*,Auto"), Margin = new Thickness(0, 1) };
            void Put(Control control, int at) { Grid.SetColumn(control, at); control.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(control); }
            // A face for every component: the brand mark of FFmpeg, a sign by its meaning for the others (MainWindow.Setup.cs).
            Put(PartFace(id), 0);
            Put(new TextBlock { Text = NameOf(id, Text(component, "name")) }, 1);
            Put(new SelectableTextBlock { Text = version.Length > 0 ? version : Lang.T("нет") }, 2);
            var dot = new Ellipse { Classes = { "dot" }, Margin = new Thickness(0, 0, 6, 0) };
            dot.Classes.Set("ok", state is "fresh" or "own");
            dot.Classes.Set("warn", state == "limited");
            dot.Classes.Set("bad", state is "old" or "missing");
            var said = state switch
            {
                // FFmpeg under an NVIDIA driver below the LTS 610.88: the older branch that keeps NVENC working.
                "limited" => Lang.F("драйвер NVIDIA {0} ниже 610.88: доступны не все операции", Text(component, "driver")),
                "fresh" => id == "plugins" ? Lang.T("все загружаются") : Lang.T("свежая"),
                "old" => id == "plugins" ? Lang.F("не загружаются: {0}", Text(component, "detail").Replace("not loaded: ", "")) : Lang.F("есть новее: {0}", latest),
                "own" => Lang.T("не сравнивается"),
                "missing" => Lang.T("не установлен"), _ => Lang.T("не проверено"),
            };
            var stateText = new TextBlock { Classes = { "caption" }, Text = said, TextTrimming = TextTrimming.CharacterEllipsis };
            ToolTip.SetTip(stateText, said);
            Put(new DockPanel { Children = { dot, stateText } }, 3);
            if (Installers.TryGetValue(id, out var op) && _told?.Find(op) is { } node)
            {
                var update = new Button { Classes = { "small" }, Content = Lang.T(version.Length > 0 ? "ОБНОВИТЬ" : "УСТАНОВИТЬ"), Margin = new Thickness(6, 0, 0, 0) };
                Avalonia.Automation.AutomationProperties.SetAutomationId(update, "update_" + id);
                ToolTip.SetTip(update, TipOf(node));
                update.IsEnabled = !_runner.Running && !_asking && !_clearing;
                update.Click += (_, _) => Press(node, null);
                Put(update, 4);
            }
            Add(row);
        }
        var checkedAt = _components is { } told && told.TryGetProperty("checked", out var when) && DateTime.TryParse(when.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.None, out var at)
            ? at.ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture) : "";
        var again = new Button { Classes = { "small" }, Content = Lang.T("ПРОВЕРИТЬ СЕЙЧАС"), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 6, 0, 0) };
        Avalonia.Automation.AutomationProperties.SetAutomationId(again, "components_refresh");
        ToolTip.SetTip(again, Lang.T("Спросить GitHub о свежем выпуске VapourSynth сейчас. Сам он спрашивается не чаще раза в сутки."));
        again.Click += async (_, _) =>
        {
            again.IsEnabled = false;
            SetStatus("Спрашиваю GitHub о свежих выпусках…");
            await LoadComponents(refresh: true);
            SetStatus("Версии компонентов прочитаны.");
        };
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        if (Needed().Count > 0)
        {
            var missing = new Button { Classes = { "small", "run" }, Content = Lang.T("УСТАНОВИТЬ ВСЁ"), Margin = new Thickness(0, 6, 0, 0) };
            Avalonia.Automation.AutomationProperties.SetAutomationId(missing, "setup_install_missing");
            ToolTip.SetTip(missing, Lang.T("Поставить по порядку все компоненты, которых ещё нет: сначала - что будет скачано, вопросом."));
            missing.IsEnabled = !_runner.Running && !_asking && !_clearing;
            missing.Click += (_, _) => InstallMissing();
            buttons.Children.Add(missing);
        }
        buttons.Children.Add(again);
        Add(buttons);
        Note(checkedAt.Length > 0 ? Lang.F("GitHub спрошен {0}.", checkedAt) : Lang.T("GitHub ещё не спрашивался."));
    }

    /// <summary>
    /// SETUP, SYSTEM: what the machine is, and the hardware encoders FFmpeg found working on it; copied as text for a
    /// report of a trouble.
    /// </summary>
    void SystemCard(Panel column)
    {
        Open(column, "СИСТЕМА");
        var lines = new List<(string Key, string Value)>();
        string Read(string key, string name)
        {
            try { return Microsoft.Win32.Registry.GetValue(key, name, null)?.ToString() ?? ""; }
            catch { return ""; }
        }
        const string Nt = @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion";
        var build = Read(Nt, "CurrentBuild");
        var ubr = Read(Nt, "UBR");
        var windows = int.TryParse(build, out var number) && number >= 22000 ? "Windows 11" : "Windows 10";
        lines.Add(("Windows", $"{windows} {Read(Nt, "EditionID")} {Read(Nt, "DisplayVersion")}".Trim() + (build.Length > 0 ? Lang.F(", сборка {0}", build + (ubr.Length > 0 ? "." + ubr : "")) : "")));
        var cpu = Read(@"HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString").Trim();
        lines.Add((Lang.T("Процессор"), (cpu.Length > 0 ? cpu + ", " : "") + Lang.F("потоков: {0}", Environment.ProcessorCount)));
        foreach (var gpu in ComponentList().Where(component => Text(component, "id") == "gpu"))
            lines.Add((Lang.T("Видеокарта"), $"{Text(gpu, "name")}" + (Text(gpu, "version").Length > 0 ? Lang.F(", драйвер {0}", Text(gpu, "version")) : "")));
        var memory = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes;
        if (memory > 0) lines.Add((Lang.T("Память"), Lang.F("{0} ГБ", (memory / 1024.0 / 1024 / 1024).ToString("0.#", CultureInfo.InvariantCulture))));
        lines.Add((Lang.T("Кодеры FFmpeg"), Coders()));
        try
        {
            var drive = new System.IO.DriveInfo(System.IO.Path.GetPathRoot(Paths.Root) ?? Paths.Root);
            lines.Add((Lang.T("Диск программы"), Lang.F("{0}: свободно {1} ГБ из {2} ГБ", drive.Name.TrimEnd('\\', ':'),
                (drive.AvailableFreeSpace / 1073741824.0).ToString("0", CultureInfo.InvariantCulture), (drive.TotalSize / 1073741824.0).ToString("0", CultureInfo.InvariantCulture))));
        }
        catch { }
        foreach (var (key, value) in lines) Pair(key, value);
        var copy = new Button { Classes = { "small" }, Content = Lang.T("СКОПИРОВАТЬ"), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 6, 0, 0) };
        Avalonia.Automation.AutomationProperties.SetAutomationId(copy, "system_copy");
        ToolTip.SetTip(copy, Lang.T("Скопировать сведения о машине текстом - для сообщения об ошибке."));
        copy.Click += async (_, _) =>
        {
            var text = Program.Product + " " + (Paths.Version ?? "") + Environment.NewLine + string.Join(Environment.NewLine, lines.Select(line => line.Key + ": " + line.Value));
            if (Clipboard is { } clipboard) await Avalonia.Input.Platform.ClipboardExtensions.SetTextAsync(clipboard, text);
            SetStatus("Сведения о машине скопированы.");
        };
        Add(copy);
    }

    /// <summary>
    /// Before an installer runs: what it would download - every file with its size and its source - asked of the places the
    /// script asks, with nothing fetched (Door.Plan), and put to the person. True - the download may go.
    /// </summary>
    async Task<bool> AskDownload(Node node)
    {
        SetStatus("Спрашиваю, что будет скачано…");
        var plan = await Door.Plan(node.Id);
        var text = new System.Text.StringBuilder();
        var culture = Lang.Code == "ru" ? new CultureInfo("ru-RU") : CultureInfo.InvariantCulture;
        string Megabytes(long bytes) => Lang.F("{0} МБ", (bytes / 1048576.0).ToString("0.0", culture));
        if (plan is { } told && told.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True)
        {
            long total = 0;
            bool unsized = false;
            text.Append(Lang.T("Будет скачано:")).Append('\n');
            foreach (var file in told.GetProperty("files").EnumerateArray())
            {
                long? size = file.TryGetProperty("size", out var bytes) && bytes.ValueKind == JsonValueKind.Number ? bytes.GetInt64() : null;
                text.Append("  ").Append(Text(file, "name")).Append(" - ").Append(size is { } known ? Megabytes(known) : Lang.T("размер не сообщён")).Append('\n');
                if (Text(file, "url") is { Length: > 0 } url) text.Append("    ").Append(url).Append('\n');
                total += size ?? 0;
                unsized |= size is null;
            }
            if (total > 0) text.Append(Lang.F("Всего: {0}", Megabytes(total))).Append(unsized ? Lang.T(" и файлы без размера") : "").Append('\n');
            if (told.TryGetProperty("notes", out var notes))
                foreach (var note in notes.EnumerateArray())
                    text.Append('\n').Append(Lang.T("Почему эта версия:")).Append(' ').Append(note.GetString()).Append('\n');
        }
        else
        {
            var why = plan is { } refused && Text(refused, "error") is { Length: > 0 } error ? error : Lang.T("консольная команда не ответила");
            text.Append(Lang.F("Заранее узнать, что будет скачано, не удалось: {0}", why)).Append('\n')
                .Append(Lang.T("Установка назовёт файлы сама, в журнале."));
        }
        SetStatus("Готово.");
        return await AskDialog.YesNo(this, Lang.F("Скачать для «{0}»?", node.Name), text.ToString().TrimEnd());
    }

    /// <summary>What the engine is made of, its licence, and where its source lies (ABOUT, COMPOSITION).</summary>
    static readonly (string Id, string Name, string Licence, string Source)[] Composition =
    {
        ("vapoursynth", "VapourSynth", "LGPL 2.1", "https://github.com/vapoursynth/vapoursynth"),
        ("plugins", "Плагины", "у каждого своя: GPL, LGPL, MIT, ISC - install\\vs_plugins.json", "https://github.com/vapoursynth/vsrepo"),
        ("ffmpeg", "FFmpeg", "GPL v3 (сборка gyan.dev full)", "ffmpeg-*-source.tar.gz"),
    };

    void CompositionCard(Panel column)
    {
        Open(column, "СОСТАВ");
        var tools = System.IO.Path.Combine(Paths.Root, "Tools");
        foreach (var (id, name, licence, source) in Composition)
        {
            var version = ComponentList().Where(component => Text(component, "id") == id).Select(component => Text(component, "version")).FirstOrDefault() ?? "";
            // The sources the GPL asks to give beside the build: the archives in Tools\, by their names.
            var where = source.StartsWith("https://", StringComparison.Ordinal) ? source
                : source.Contains('*') && System.IO.Directory.Exists(tools)
                    ? string.Join(", ", System.IO.Directory.GetFiles(tools, source).Select(path => @"Tools\" + System.IO.Path.GetFileName(path)))
                    : @"Tools\" + source;
            var row = new Grid { ColumnDefinitions = new ColumnDefinitions("22,96,110,250,*"), Margin = new Thickness(0, 1) };
            void Put(Control control, int at) { Grid.SetColumn(control, at); control.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(control); }
            // A face for every component: the brand mark of FFmpeg, a sign by its meaning for the others (MainWindow.Setup.cs).
            Put(PartFace(id), 0);
            Put(new TextBlock { Text = Lang.T(name) }, 1);
            Put(new SelectableTextBlock { Text = version.Length > 0 ? version : "—" }, 2);
            Put(new TextBlock { Classes = { "caption" }, Text = Lang.T(licence), TextWrapping = TextWrapping.Wrap }, 3);
            Put(new SelectableTextBlock { Classes = { "caption" }, Text = where.Length > 0 ? where : "—", TextWrapping = TextWrapping.Wrap }, 4);
            Add(row);
        }
        Note("Движок - отдельные программы со своими лицензиями: программа зовёт их, а не встраивает. В выпуск они не входят: их ставит SETUP, исходники GPL-сборки FFmpeg лежат рядом с ней в Tools.");
    }

    /// <summary>The hardware encoders FFmpeg was found to work with on this machine (config\hardware_capabilities_cache.json).</summary>
    string Coders()
    {
        try
        {
            var file = System.IO.Path.Combine(Paths.Config, "hardware_capabilities_cache.json");
            if (!System.IO.File.Exists(file)) return Lang.T("не проверялись: СЕРВИС → Возможности оборудования");
            using var told = JsonDocument.Parse(System.IO.File.ReadAllText(file));
            var ok = told.RootElement.GetProperty("encoders").EnumerateObject()
                .Where(encoder => encoder.Value.TryGetProperty("status", out var status) && status.GetString() == "OK").Select(encoder => encoder.Name).ToList();
            return ok.Count > 0 ? string.Join(", ", ok) : Lang.T("ни один аппаратный не прошёл проверку");
        }
        catch { return Lang.T("кэш проверки не читается"); }
    }

    void ShowComponents()
    {
        ComponentRow.Children.Clear();
        if (_components is not { } told || !told.TryGetProperty("components", out var list)) return;
        var checkedAt = told.TryGetProperty("checked", out var when) && DateTime.TryParse(when.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.None, out var at)
            ? at.ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture) : "";
        foreach (var component in list.EnumerateArray())
        {
            string Text(string name) => component.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
            ComponentRow.Children.Add(Badge(Text("id"), Text("name"), Text("version"), Text("detail"), Text("latest"), Text("state"), Text("source"), Text("brand"), Text("driver"), checkedAt));
        }
    }

    static Control Badge(string id, string name, string version, string detail, string latest, string state, string source, string brand, string driver, string checkedAt)
    {
        var dot = new Ellipse { Classes = { "dot" } };
        dot.Classes.Set("ok", state is "fresh" or "own");
        dot.Classes.Set("warn", state == "limited");
        dot.Classes.Set("bad", state is "old" or "missing");
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center, Children = { dot } };
        var mark = Icons.Mark(MarkOf(id, brand));
        if (mark is not null) row.Children.Add(mark);
        // A mark says whose it is; VapourSynth and the plugins have none, and a GPU without a known maker has its name.
        else row.Children.Add(new TextBlock { Classes = { "caption" }, Text = id == "gpu" ? Lang.T("GPU") : NameOf(id, name) });
        var shown = id == "plugins" && version.Contains('/') ? Lang.F("{0} из {1}", version.Split('/')[0], version.Split('/')[1]) : version;
        row.Children.Add(new TextBlock { Classes = { "caption", "version" }, Text = shown.Length > 0 ? shown : Lang.T("нет") });

        var tip = new System.Text.StringBuilder(NameOf(id, name) + (shown.Length > 0 ? " " + shown : ""));
        if (detail.Length > 0 && detail != version && id != "plugins") tip.Append('\n').Append(detail);
        tip.Append('\n').Append(state switch
        {
            "fresh" => id == "plugins" ? Lang.T("Ядро загружает все плагины набора install\\vs_plugins.json.") : Lang.T("Это свежий выпуск."),
            "old" => id switch
            {
                "plugins" => Lang.F("Ядро не загружает: {0}. Поставить заново - SETUP → Установить плагины.", detail.Replace("not loaded: ", "")),
                "ffmpeg" => Lang.F("Вышел более новый FFmpeg: {0}. Обновить - SETUP.", latest),
                _ => Lang.F("Вышел более новый выпуск: {0}. После обновления VapourSynth - снова плагины: SETUP.", latest),
            },
            "limited" => Lang.F("Драйвер NVIDIA {0} ниже 610.88 - LTS-драйвера, под который собраны программы: стоит FFmpeg {1}, при которой работает NVENC, и доступны не все операции.", driver, version),
            "own" => id == "gpu"
                ? Lang.T("Драйвер видеокарты ставите вы: программа его не сравнивает, только показывает. От него зависит сборка FFmpeg с NVENC.")
                : Lang.T("Эту часть программа не сравнивает, только показывает."),
            "missing" => Lang.T("Не установлен: установить - SETUP."),
            _ => Lang.T("Свежесть не проверена: GitHub не ответил."),
        });
        if (source.Length > 0) tip.Append('\n').Append(Lang.F("Свежий выпуск смотрится в {0}", source));
        if (source.Length > 0 && checkedAt.Length > 0) tip.Append('\n').Append(Lang.F("Проверено: {0}", checkedAt));
        var badge = new Border { Classes = { "verbadge" }, Child = row };
        ToolTip.SetTip(badge, tip.ToString());
        Avalonia.Automation.AutomationProperties.SetAutomationId(badge, "component_" + (id == "gpu" ? "gpu_" + brand : id));
        return badge;
    }
}
