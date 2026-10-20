using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using AudionVSEngine.Core;
using AudionVSEngine.Views;

namespace AudionVSEngine;

/// <summary>
/// The engine is not installed - VapourSynth or FFmpeg is missing (vs_cli.cmd components): a page that needs it shows its
/// installers in their order in place of its form, each with what it would download - the files, their source and
/// size - asked of the places the script asks, nothing fetched (vs_cli.cmd plan). A press runs the installer as SERVICE
/// runs it; the badges and this block are read again when it ends. A neural preset on a machine with an NVIDIA RTX card
/// and without vs-mlrt shows the installation of MLRT the same way (the owner, 18.10.2026: "система определяет наличие
/// RTX и добавляет кнопку установки MLRT").
/// </summary>
public partial class MainWindow
{
    /// <summary>The installers of the engine in the order they are run; the ones the program does not have stay out.</summary>
    static readonly string[] EngineSteps = { "install_vapoursynth", "install_vs_plugins", "install_ffmpeg" };
    static readonly string[] MlrtSteps = { "install_mlrt" };

    /// <summary>What each installer would download, as the plan said it: one line, asked once a start; and how many bytes.</summary>
    readonly Dictionary<string, string> _plans = new();
    readonly Dictionary<string, long> _planBytes = new();
    /// <summary>The names of the files each installer would download, and how many of them have no size said.</summary>
    readonly Dictionary<string, (List<string> Names, int Unsized)> _planFiles = new();
    bool _planning;

    /// <summary>The parts of the engine the console command found missing: "vapoursynth", "plugins", "ffmpeg".</summary>
    HashSet<string> Missing() => ComponentList().Where(component => Text(component, "state") == "missing")
        .Select(component => Text(component, "id")).ToHashSet();

    /// <summary>The page in sight needs the engine and the engine is not there: the installers stand in place of its form.</summary>
    void ShowEngine()
    {
        if (_view is not { } view) { EngineHost.IsVisible = false; return; }
        var missing = _components is null ? new HashSet<string>() : Missing();
        bool engine = view.Page.Node.Engine && (missing.Contains("vapoursynth") || missing.Contains("ffmpeg"));
        // A neural preset is in the window only with an RTX card or MLRT (Core\Manifest.cs): without MLRT - its installation.
        bool mlrt = !engine && view.Page.Node.NeedsMlrt && _told is { Machine.Mlrt.Length: 0 };
        bool blocked = engine || mlrt;
        EngineHost.IsVisible = blocked;
        view.Root.IsVisible = !blocked;
        if (engine) FillEngine(missing);
        else if (mlrt) FillEngine(missing, neural: true);
        ShowPreview(view, blocked);
    }

    void FillEngine(HashSet<string> missing, bool neural = false)
    {
        EngineBody.Children.Clear();
        EngineBody.Children.Add(new TextBlock { Classes = { "grp" }, Text = Lang.T(neural ? "MLRT НЕ УСТАНОВЛЕН" : "ДВИЖОК НЕ УСТАНОВЛЕН") });
        EngineBody.Children.Add(new TextBlock
        {
            Classes = { "note" }, TextWrapping = Avalonia.Media.TextWrapping.Wrap,
            Text = neural
                ? Lang.F("Нейросетевым пресетам нужен vs-mlrt: TensorRT под видеокарту {0}, ONNX Runtime и модели. Ставится в папку движка, в Windows ничего не пишется; первый прогон каждой модели собирает движок TensorRT, 30-120 с.", _told?.Machine.Rtx ?? "")
                : Lang.T("Пресетам нужен VapourSynth с плагинами и FFmpeg. Всё ставится в папку программы, в Windows ничего не пишется. Порядок - сверху вниз."),
        });
        int step = 0;
        foreach (var id in neural ? MlrtSteps : EngineSteps)
        {
            if (_told?.Find(id) is not { } node) continue;
            step++;
            var part = id switch { "install_vapoursynth" => "vapoursynth", "install_vs_plugins" => "plugins", "install_ffmpeg" => "ffmpeg", "install_mlrt" => "mlrt", _ => "" };
            bool needed = part == "mlrt" ? _told is { Machine.Mlrt.Length: 0 } : part.Length > 0 && missing.Contains(part);
            var title = new TextBlock { Classes = { "blockname" }, Text = $"{step}. {Upper(node.Name)}", VerticalAlignment = VerticalAlignment.Center };
            var state = new TextBlock
            {
                Classes = { "caption" }, Margin = new Thickness(10, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center,
                Text = needed ? Lang.T("не установлен") : part.Length > 0 ? Lang.T("установлен") : "",
            };
            var run = new Button { Classes = { "small" }, Content = Lang.T(needed ? "УСТАНОВИТЬ" : "ПОСТАВИТЬ ЗАНОВО"), HorizontalAlignment = HorizontalAlignment.Right };
            if (needed) run.Classes.Add("run");
            Avalonia.Automation.AutomationProperties.SetAutomationId(run, "engine_" + id);
            ToolTip.SetTip(run, TipOf(node));
            run.IsEnabled = !_runner.Running && !_asking && !_clearing;
            run.Click += (_, _) => Press(node, null);
            var head = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto"), Children = { title, state, run } };
            Grid.SetColumn(state, 1);
            Grid.SetColumn(run, 2);
            var plan = new TextBlock
            {
                Classes = { "caption" }, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0),
                Text = _plans.TryGetValue(id, out var said) ? said : Lang.T("Что будет скачано - спрашиваю…"),
            };
            var body = new StackPanel { Children = { head, new TextBlock { Classes = { "note" }, Text = node.About, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) }, plan } };
            EngineBody.Children.Add(new Border { Classes = { "block" }, Child = body });
        }
        if (Lang.Code != "ru") Lang.Walk(EngineBody);
        AskPlans();
        CentreWords();
    }

    /// <summary>The plans of the installers, asked once a start off the window's thread; the block is written again with them.</summary>
    async void AskPlans()
    {
        if (_planning || _told is null) return;
        var wanted = EngineSteps.Concat(MlrtSteps).Where(id => _told.Find(id) is not null && !_plans.ContainsKey(id)).ToList();
        if (wanted.Count == 0) return;
        _planning = true;
        try { await PlansOf(wanted); }
        finally { _planning = false; }
        if (EngineHost.IsVisible) ShowEngine();
    }

    /// <summary>What the installers named would download - the files, their size - asked of the console command (vs_cli.cmd plan).</summary>
    async Task PlansOf(IEnumerable<string> ids)
    {
        var culture = Lang.Code == "ru" ? new CultureInfo("ru-RU") : CultureInfo.InvariantCulture;
        foreach (var id in ids.Where(id => !_plans.ContainsKey(id)).ToList())
        {
            var plan = await Door.Plan(id);
            if (plan is { } told && told.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True)
            {
                var files = told.GetProperty("files").EnumerateArray().ToList();
                long known = files.Sum(file => file.TryGetProperty("size", out var size) && size.ValueKind == JsonValueKind.Number ? size.GetInt64() : 0);
                int unsized = files.Count(file => !file.TryGetProperty("size", out var size) || size.ValueKind != JsonValueKind.Number);
                var names = string.Join(", ", files.Take(4).Select(file => Text(file, "name")));
                _plans[id] = Lang.F("Будет скачано файлов: {0}, {1} МБ", files.Count, (known / 1048576.0).ToString("0", culture))
                    + (unsized > 0 ? Lang.F(" и {0} без размера", unsized) : "") + ": " + names + (files.Count > 4 ? ", …" : "");
                _planBytes[id] = known;
                _planFiles[id] = (files.Select(file => Text(file, "name")).ToList(), unsized);
            }
            else _plans[id] = Lang.T("Заранее узнать, что будет скачано, не удалось: установка назовёт файлы сама.");
        }
    }
}
