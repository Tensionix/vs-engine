using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using AudionVSEngine.Core;
using AudionVSEngine.Views;

namespace AudionVSEngine;

/// <summary>
/// SETUP: the additional components the program works with - VapourSynth, its plugins, FFmpeg and, with an NVIDIA RTX
/// card, MLRT - their versions, their installation, update and removal. A button of its own in the header, apart from
/// the switches of the window itself (the owner, 18.10.2026: "Желательно делать Setup отдельно от тех переключателей
/// окон, которые являются для работы самого окна, а не для того, чтобы вообще всё работало"); the operations are `setup`
/// of the layout. At every start of the window a component that is not installed is asked about (Views\SetupDialog.cs):
/// INSTALL installs them one after another as SETUP does; INSTALL LATER says where SETUP is.
/// </summary>
public partial class MainWindow
{
    /// <summary>The installers in the order they run - the plugins and MLRT go into VapourSynth - and the part each puts in place.</summary>
    static readonly (string Op, string Part)[] SetupSteps =
    {
        ("install_vapoursynth", "vapoursynth"), ("install_vs_plugins", "plugins"), ("install_ffmpeg", "ffmpeg"), ("install_mlrt", "mlrt"),
    };

    /// <summary>The start asked once: the components are read again after every install, the question is not.</summary>
    bool _setupAsked;

    /// <summary>The installers agreed to, waiting their turn: the next starts when one has ended done.</summary>
    readonly Queue<Node> _setupQueue = new();

    void WireSetup() => SetupButton.Click += (_, _) => ToggleSheet("setup");

    /// <summary>OPEN SETUP of the question of the start: the sheet as the button of the header opens it; left open if it is.</summary>
    void OpenSetup()
    {
        if (_sheet != "setup") ToggleSheet("setup");
    }

    /// <summary>
    /// The installers of what is not in place: a part the console command found missing; the plugins too when not all of
    /// them load or VapourSynth itself is missing; MLRT only where an NVIDIA RTX card is (vs_cli.cmd components names it there).
    /// </summary>
    List<(Node Node, string Part)> Needed()
    {
        var needed = new List<(Node, string)>();
        if (_told is null || _components is null) return needed;
        var states = ComponentList().ToDictionary(component => Text(component, "id"), component => Text(component, "state"));
        bool engine = states.TryGetValue("vapoursynth", out var vs) && vs == "missing";
        foreach (var (op, part) in SetupSteps)
        {
            if (!_told.Layout.Setup.Contains(op) || _told.Find(op) is not { } node) continue;
            var state = states.TryGetValue(part, out var said) ? said : "";
            bool missing = part switch
            {
                "plugins" => engine || state is "missing" or "old",
                "mlrt" => _told.Machine.Rtx.Length > 0 && state == "missing",
                _ => state == "missing",
            };
            if (missing) needed.Add((node, part));
        }
        return needed;
    }

    /// <summary>The dot of SETUP: something is not installed; its tooltip names what.</summary>
    void ShowSetupMark()
    {
        var needed = Needed();
        SetupDot.IsVisible = needed.Count > 0;
        ToolTip.SetTip(SetupDot, needed.Count > 0 ? Lang.F("Не установлено: {0}", string.Join(", ", needed.Select(one => PartName(one.Part)))) : null);
    }

    /// <summary>
    /// The sign of a component that has no brand mark: VapourSynth - the graph of a processing, the plugins - a piece of a
    /// puzzle, MLRT - a neural network (the owner, 18.10.2026: "Недостающие иконки - смотрятся как баг. Можно добавить
    /// подходящие по смыслу").
    /// </summary>
    static string PartSign(string part) => part switch { "vapoursynth" => "workflow", "plugins" => "puzzle", "mlrt" => "brain-circuit", _ => "package" };

    /// <summary>The face of a component: its brand mark (FFmpeg), else its sign.</summary>
    static Control PartFace(string part, double size = 13) => Icons.Mark(part, size) is { } mark ? mark : Icons.Sign(PartSign(part));

    /// <summary>A download in megabytes, or in gigabytes from one.</summary>
    static string SizeText(long bytes)
    {
        if (bytes <= 0) return "";
        var culture = Lang.Code == "ru" ? new CultureInfo("ru-RU") : CultureInfo.InvariantCulture;
        return bytes >= 1L << 30
            ? Lang.F("{0} ГБ", (bytes / (double)(1L << 30)).ToString("0.0", culture))
            : Lang.F("{0} МБ", (bytes / 1048576.0).ToString("0", culture));
    }

    /// <summary>The files of a download in a line: the first three by their names, the rest counted.</summary>
    string FilesText(string op)
    {
        if (!_planFiles.TryGetValue(op, out var files) || files.Names.Count == 0) return Lang.T("Что будет скачано, установка назовёт сама.");
        var shown = string.Join(", ", files.Names.Take(3)) + (files.Names.Count > 3 ? Lang.F(" и ещё {0}", files.Names.Count - 3) : "");
        return Lang.F("Файлы: {0}", shown) + (files.Unsized > 0 ? Lang.F(" · размер {0} из них не сообщён", files.Unsized) : "");
    }

    /// <summary>The total of the downloads: about so much when every size is known, at least so much when some are not.</summary>
    string TotalText(IReadOnlyCollection<string> ops)
    {
        long bytes = ops.Sum(op => _planBytes.TryGetValue(op, out var size) ? size : 0);
        if (bytes <= 0) return Lang.T("Сколько будет скачано, установка назовёт сама.");
        return ops.All(_planBytes.ContainsKey)
            ? Lang.F("Всего к скачиванию: около {0}.", SizeText(bytes))
            : Lang.F("Всего к скачиванию: не меньше {0}; размер остального установка назовёт сама.", SizeText(bytes));
    }

    /// <summary>A component in the question: its face, name, what it is for, the size and the files of its download.</summary>
    SetupDialog.Item ItemOf(string op, string part, string? card = null) => new(part, PartFace(part, 15), PartName(part),
        card is null ? PartWhy(part) : Lang.F("Нейросетевые пресеты DPIR, Real-ESRGAN и Пересборка мягкого HD на видеокарте {0}: TensorRT, ONNX Runtime и модели.", card),
        SizeText(_planBytes.TryGetValue(op, out var bytes) ? bytes : 0), FilesText(op));

    static string PartName(string part) => part switch
    {
        "vapoursynth" => "VapourSynth", "plugins" => Lang.T("Плагины VapourSynth"), "ffmpeg" => "FFmpeg", "mlrt" => "MLRT", _ => part,
    };

    string PartWhy(string part) => part switch
    {
        "vapoursynth" => Lang.T("Движок обработки: каждый пресет - сценарий VapourSynth."),
        "plugins" => Lang.T("Фильтры пресетов: BM3D, DFTTest, QTGMC, дебанд, зерно и другие."),
        "ffmpeg" => Lang.T("Пишет результат: x264, x265, ProRes, DNxHR и звук."),
        "mlrt" => Lang.F("Нейросетевые пресеты DPIR, Real-ESRGAN и Пересборка мягкого HD на видеокарте {0}: TensorRT, ONNX Runtime и модели.", _told?.Machine.Rtx ?? ""),
        _ => "",
    };

    /// <summary>The start: the components are read; something is not installed - the question, once a start.</summary>
    async Task AskSetupAtStart()
    {
        if (_setupAsked) return;
        _setupAsked = true;
#if DEBUG
        // The pictures of a check are of the window as it stands, not of a question over it.
        if (Program.ShotFolder.Length > 0) return;
#endif
        if (Needed().Count == 0) return;
        if (await AskSetup(later: true) is { } agreed) StartSetup(agreed);
        else if (_sheet != "setup") SetStatus("Дополнительные компоненты не установлены: их ставит SETUP в шапке окна.");
    }

    /// <summary>
    /// The question: every part to install with what it is for and what will be downloaded (asked of the installers, nothing
    /// fetched). The installers agreed to, or null - later, or cancelled.
    /// </summary>
    async Task<List<Node>?> AskSetup(bool later)
    {
        var needed = Needed();
        if (needed.Count == 0 || _runner.Running || _asking || _clearing) return null;
        // What will be downloaded is asked first, the window free meanwhile: the question waits for the answer, not the window.
        SetStatus("Спрашиваю, что будет скачано…");
        await PlansOf(needed.Select(one => one.Node.Id));
        SetStatus("Готово.");
        if (_runner.Running || _asking || _clearing || !IsVisible) return null;
        _asking = true;
        ApplyBusy();
        try
        {
            var items = needed.Select(one => ItemOf(one.Node.Id, one.Part)).ToList();
            var total = TotalText(needed.Select(one => one.Node.Id).ToList());
            switch (await SetupDialog.Ask(this, items, total, later))
            {
                case SetupDialog.Answer.Install: return needed.Select(one => one.Node).ToList();
                case SetupDialog.Answer.Open: OpenSetup(); return null;
                default: return null;
            }
        }
        finally
        {
            _asking = false;
            ApplyBusy();
        }
    }

    /// <summary>The installers agreed to, one after another: the downloads were agreed to in the question.</summary>
    void StartSetup(IEnumerable<Node> nodes)
    {
        _setupQueue.Clear();
        foreach (var node in nodes) _setupQueue.Enqueue(node);
        NextSetup();
    }

    void NextSetup()
    {
        if (_setupQueue.Count == 0 || _runner.Running || _told is null) return;
        var node = _setupQueue.Dequeue();
        Begin(node, _target, "{}", new Dictionary<string, string>(), "SETUP → " + node.Name, source: _source);
    }

    /// <summary>A run of SETUP has ended: done - the next installer; anything else - the rest waits for SETUP.</summary>
    void SetupEnded(string outcome)
    {
        if (_setupQueue.Count == 0) return;
        if (outcome == "done") { NextSetup(); return; }
        var left = string.Join(", ", _setupQueue.Select(node => node.Name));
        _setupQueue.Clear();
        SetStatus(Lang.F("Установка остановлена, не поставлено: {0}. Причина - в терминале; продолжить - SETUP в шапке окна.", left));
    }

    // ------------------------------------------------------------ the sheet

    /// <summary>SETUP: the components with their versions and buttons, the machine, the engine and its removal.</summary>
    void FillSetup()
    {
        Head("SETUP");
        SheetBody.Children.Add(new TextBlock
        {
            Classes = { "note" }, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 10),
            Text = Lang.T("Дополнительные компоненты, с которыми работает программа: VapourSynth с плагинами и FFmpeg, а при видеокарте NVIDIA RTX - ещё MLRT для нейросетевых пресетов. У каждого своя лицензия, они ставятся отдельно, с сайтов авторов, в папку программы; в Windows ничего не пишется."),
        });
        var (left, right) = Columns();
        ComponentsCard(left);
        EngineCard(left);
        SystemCard(right);
    }

    /// <summary>SETUP, ENGINE: where it lives, and its removal to the Recycle Bin.</summary>
    void EngineCard(Panel column)
    {
        if (_told?.Find("remove_vapoursynth") is not { } node || !_told.Layout.Setup.Contains(node.Id)) return;
        Open(column, "ДВИЖОК");
        Note(Lang.T("Папка system_core\\vapoursynth: VapourSynth, его плагины и MLRT. Удаляется в Корзину; SETUP поставит его снова."));
        var remove = new Button { Classes = { "small", "burn" }, Content = Upper(node.Name), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 6, 0, 0) };
        Avalonia.Automation.AutomationProperties.SetAutomationId(remove, "run_" + node.Id);
        ToolTip.SetTip(remove, TipOf(node));
        remove.IsEnabled = !_runner.Running && !_asking && !_clearing;
        remove.Click += (_, _) => Press(node, null);
        Add(remove);
    }

    /// <summary>INSTALL ALL of SETUP: the same question as at the start, with CANCEL.</summary>
    async void InstallMissing()
    {
        if (await AskSetup(later: false) is { } agreed) StartSetup(agreed);
    }
}
