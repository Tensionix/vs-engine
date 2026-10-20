using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Ellipse = Avalonia.Controls.Shapes.Ellipse;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using AudionVSEngine.Core;

namespace AudionVSEngine;

/// <summary>
/// The preview: in the lower left corner, under the form, the middle frame of a video of the Source before and after the
/// preset of the page with its values - the preview of Audion Image Tools (the owner, 18.10.2026: "Может выделим превью
/// (прямо как в e:\TOOLS\Audion Image Tools\): программа будет брать кадр в середине и давать внизу расчёт только для
/// него при любом движении и переключении через секунду-две когда юзер не трогает ничего"). Media Tools works with
/// files; VS Engine works with the picture, and a look is chosen by eye.
///
/// The window draws nothing of its own: the console command renders the frame through the same .vpy with the same
/// values a run would take (vs_cli.cmd frame - system_core\core\frame.py) and hands back the two pictures. A change of a
/// field, another page, another Source, another video of it - the frame is counted again once nothing has been touched
/// for a moment; a count asked before a newer one is ended, and its answer dropped. The pages of a preset and of a
/// profile show it (a run that can say its commands: Node.DryRun).
/// </summary>
public partial class MainWindow
{
    /// <summary>The width of the frame of two 16:9: never less, never more, whatever the room. Wider than in Image Tools: the
    /// picture is what a preset is chosen by.</summary>
    const double FrameLeast = 380, FrameMost = 900;
    /// <summary>The share of the work area the preview keeps when the form is taller than the room over it: the form scrolls
    /// over the preview, the preview stays (the owner, 18.10.2026: "превью закрепить и проматывать лишь область выше").</summary>
    const double PreviewShare = 0.42;
    /// <summary>The width the controls and the facts take at the right of the frame.</summary>
    const double SideWidth = 290;
    /// <summary>The least height left to the form over the preview.</summary>
    const double FormLeast = 170;
    /// <summary>Where in a video the frame is taken: its middle.</summary>
    const double FrameAt = 0.5;

    /// <summary>The frame is asked once nothing has been touched for this long: a slider dragged, a switch tried - one count.</summary>
    readonly DispatcherTimer _previewSoon = new() { Interval = TimeSpan.FromMilliseconds(1200) };
    int _previewAt, _previewAsked;
    string _previewMode = "both";
    bool _previewFolded;
    double _frameWidth = FrameMost;
    bool _sideBeside = true;
    StackPanel _pvSide = null!;
    Bitmap? _previewBefore, _previewAfter;
    Values? _previewValues;
    TextBlock _pvName = null!, _pvCount = null!, _pvFacts = null!, _pvState = null!;
    Ellipse _pvDot = null!;
    Grid _pvPictures = null!;
    Border _pvFrame = null!;
    readonly List<ToggleButton> _pvModes = new();
    Button _pvFold = null!;
    /// <summary>The videos of the Source a run takes, as the form server counts them (folders: queue.files).</summary>
    List<string> _previewFiles = new();
    CancellationTokenSource? _previewCancel;

    void WirePreview()
    {
        Button Tool(string icon, string tip, string id, Action act)
        {
            var button = new Button { Classes = { "tool" }, Content = Icons.Sign(icon), VerticalAlignment = VerticalAlignment.Center };
            ToolTip.SetTip(button, Lang.T(tip));
            Avalonia.Automation.AutomationProperties.SetAutomationId(button, id);
            button.Click += (_, _) => act();
            return button;
        }

        // The frame of the pictures, at the left.
        _pvPictures = new Grid();
        _pvFrame = new Border { Classes = { "listbg" }, CornerRadius = new CornerRadius(5), Padding = new Thickness(6), ClipToBounds = true, Child = _pvPictures, VerticalAlignment = VerticalAlignment.Top };

        // At its right, every control of the preview, the facts under them.
        var side = _pvSide = new StackPanel { Margin = new Thickness(12, 0, 0, 0), Spacing = 6 };
        var title = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        title.Children.Add(new TextBlock { Classes = { "cardtitle" }, Text = Lang.T("ПРЕДПРОСМОТР"), VerticalAlignment = VerticalAlignment.Center });
        _pvFold = Tool("minimize-2", "Свернуть предпросмотр: форме - всё место", "preview_fold", () => { _previewFolded = !_previewFolded; FoldPreview(); });
        title.Children.Add(Tool("refresh-cw", "Посчитать кадр снова", "preview_again", () => { _ = RefreshPreview(); }));
        title.Children.Add(_pvFold);
        side.Children.Add(title);
        _pvName = new TextBlock { Classes = { "note" }, TextTrimming = TextTrimming.CharacterEllipsis };
        Avalonia.Automation.AutomationProperties.SetAutomationId(_pvName, "preview_name");
        side.Children.Add(_pvName);
        var tools = new WrapPanel { Orientation = Orientation.Horizontal };
        var steps = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, Margin = new Thickness(0, 0, 10, 4) };
        steps.Children.Add(Tool("chevron-left", "Предыдущее видео источника", "preview_back", () => StepPreview(-1)));
        _pvCount = new TextBlock { Classes = { "note" }, VerticalAlignment = VerticalAlignment.Center, MinWidth = 44, TextAlignment = TextAlignment.Center };
        Avalonia.Automation.AutomationProperties.SetAutomationId(_pvCount, "preview_count");
        steps.Children.Add(_pvCount);
        steps.Children.Add(Tool("chevron-right", "Следующее видео источника", "preview_next", () => StepPreview(+1)));
        tools.Children.Add(steps);
        var modes = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 6, 4) };
        foreach (var (key, word, tip) in new[]
                 {
                     ("before", "До", "Кадр источника, как его загружают пресеты."),
                     ("after", "После", "Кадр с пресетом и значениями этой страницы."),
                     ("both", "Рядом", "До и после рядом."),
                 })
        {
            var mode = new ToggleButton { Classes = { "switch" }, Content = Lang.T(word), Tag = key, Margin = new Thickness(0, 0, 4, 0), IsChecked = key == _previewMode };
            ToolTip.SetTip(mode, Lang.T(tip));
            Avalonia.Automation.AutomationProperties.SetAutomationId(mode, "preview_" + key);
            mode.Click += (_, _) => { _previewMode = key; foreach (var one in _pvModes) one.IsChecked = (string?)one.Tag == key; ShowPictures(); };
            _pvModes.Add(mode);
            modes.Children.Add(mode);
        }
        tools.Children.Add(modes);
        side.Children.Add(tools);
        _pvFacts = new TextBlock { Classes = { "note" }, TextWrapping = TextWrapping.Wrap };
        Avalonia.Automation.AutomationProperties.SetAutomationId(_pvFacts, "preview_facts");
        // The state, behind a dot that breathes while the frame is counted - the dot of the live line of a run.
        _pvDot = new Ellipse { Classes = { "livedot" }, Margin = new Thickness(0, 4, 8, 0), VerticalAlignment = VerticalAlignment.Top, IsVisible = false };
        _pvState = new TextBlock { Classes = { "note" }, TextWrapping = TextWrapping.Wrap };
        Avalonia.Automation.AutomationProperties.SetAutomationId(_pvState, "preview_state");
        var state = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*") };
        state.Children.Add(_pvDot);
        Grid.SetColumn(_pvState, 1);
        state.Children.Add(_pvState);
        side.Children.Add(_pvFacts);
        side.Children.Add(state);

        var band = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), RowDefinitions = new RowDefinitions("Auto,Auto") };
        band.Children.Add(_pvFrame);
        Grid.SetColumn(side, 1);
        band.Children.Add(side);
        PreviewCard.Child = band;

        _previewSoon.Tick += (_, _) => { _previewSoon.Stop(); _ = RefreshPreview(); };
        WorkArea.LayoutUpdated += (_, _) => FitPreview();
    }

    /// <summary>A page comes into sight: the preview is shown when it can picture it, and listens to its fields.</summary>
    void ShowPreview(PageView view, bool installers)
    {
        bool on = view.Page.Node.DryRun && !installers && Door.Ready && view.Opened;
        PreviewCard.IsVisible = on;
        if (_previewValues is not null) _previewValues.Changed -= PreviewHeard;
        _previewValues = on ? view.Values : null;
        if (_previewValues is not null) _previewValues.Changed += PreviewHeard;
        if (!on) { CancelPreview(); return; }
        PreviewSoon();
    }

    void PreviewHeard(string _) => PreviewSoon();

    /// <summary>The frame is asked again once nothing has been touched for a moment; a count still going is ended now.</summary>
    void PreviewSoon()
    {
        if (!PreviewCard.IsVisible || _previewFolded) return;
        CancelPreview();
        _previewSoon.Stop();
        _previewSoon.Start();
    }

    void CancelPreview()
    {
        _previewCancel?.Cancel();
        _previewCancel = null;
    }

    /// <summary>The videos of the Source changed (the form server counted them again): the preview follows.</summary>
    void PreviewFiles(List<string> files)
    {
        if (files.SequenceEqual(_previewFiles, StringComparer.OrdinalIgnoreCase)) return;
        _previewFiles = files;
        _previewAt = 0;
        PreviewSoon();
    }

    void StepPreview(int by)
    {
        _previewAt += by;
        PreviewSoon();
    }

    void FoldPreview()
    {
        _pvFrame.IsVisible = !_previewFolded;
        _pvFacts.IsVisible = _pvState.IsVisible = !_previewFolded;
        _pvFold.Content = Icons.Sign(_previewFolded ? "maximize-2" : "minimize-2");
        ToolTip.SetTip(_pvFold, Lang.T(_previewFolded ? "Развернуть предпросмотр" : "Свернуть предпросмотр: форме - всё место"));
        if (_previewFolded) CancelPreview();
        else PreviewSoon();
    }

    /// <summary>
    /// The frame as wide as the card allows beside the controls - between its least and its most - and as high as two
    /// 16:9 of that width; lower when the room under the form is less. The controls go over the frame when the card is
    /// too narrow for both side by side.
    /// </summary>
    void FitPreview()
    {
        if (!PreviewCard.IsVisible || _previewFolded || _view is null) return;
        double area = WorkArea.Bounds.Height, card = PreviewCard.Bounds.Width - PreviewCard.Padding.Left - PreviewCard.Padding.Right;
        if (area <= 0 || card <= 0) return;
        double rim = _pvFrame.Padding.Left + _pvFrame.Padding.Right;
        bool beside = card - SideWidth - 12 - rim >= FrameLeast;
        double width = beside ? Math.Clamp(card - SideWidth - 12 - rim, FrameLeast, FrameMost) : Math.Min(card - rim, FrameMost);
        // The room under the form: the frame grows no higher than it, down to the least width.
        double form = _view.Cards.DesiredSize.Height + _view.Cards.Margin.Top + _view.Cards.Margin.Bottom + 6;
        double chrome = PreviewCard.Padding.Top + PreviewCard.Padding.Bottom + PreviewCard.Margin.Bottom + _pvFrame.Padding.Top + _pvFrame.Padding.Bottom + 2
                        + (beside ? 0 : _pvSide.DesiredSize.Height + 6);
        double room = Math.Min(Math.Max(area - form, area * PreviewShare), area - FormLeast) - chrome;
        if (HeightOf(width) > room) width = Math.Max(FrameLeast, Math.Min(width, WidthOf(room)));
        if (Math.Abs(width - _frameWidth) > 2 || beside != _sideBeside)
        {
            _frameWidth = width;
            _sideBeside = beside;
            Grid.SetColumnSpan(_pvSide, beside ? 1 : 2);
            Grid.SetColumn(_pvSide, beside ? 1 : 0);
            Grid.SetRow(_pvFrame, beside ? 0 : 1);
            _pvSide.Margin = beside ? new Thickness(12, 0, 0, 0) : new Thickness(0, 0, 0, 6);
            SizeFrame();
        }
    }

    /// <summary>The rule between "before" and "after", with its air at both sides.</summary>
    const double Between = 13;

    /// <summary>Two 16:9 side by side with the rule between them: their height for a width, and the width for a height.</summary>
    static double HeightOf(double width) => (width - Between) / 2 * 9 / 16;

    static double WidthOf(double height) => height * 16 / 9 * 2 + Between;

    void SizeFrame()
    {
        _pvPictures.Width = _frameWidth;
        _pvPictures.Height = HeightOf(_frameWidth);
    }

    async Task RefreshPreview()
    {
        if (_view is not { } view || !PreviewCard.IsVisible || _previewFolded || !view.Opened) return;
        var node = view.Page.Node;
        if (_previewFiles.Count == 0)
        {
            _pvName.Text = "";
            _pvCount.Text = "0 / 0";
            _previewBefore = _previewAfter = null;
            _pvFacts.Text = "";
            Say(Lang.T("В источнике нет видео: предпросмотру нечего показать."), "");
            ShowPictures();
            return;
        }
        if (view.Values.Refusal.Length > 0) { Say(view.Values.Refusal, "bad"); return; }
        _previewAt = ((_previewAt % _previewFiles.Count) + _previewFiles.Count) % _previewFiles.Count;
        var file = _previewFiles[_previewAt];
        _pvName.Text = Path.GetFileName(file);
        ToolTip.SetTip(_pvName, Paths.Short(file));
        _pvCount.Text = $"{_previewAt + 1} / {_previewFiles.Count}";
        CancelPreview();
        var cancel = _previewCancel = new CancellationTokenSource();
        int asked = ++_previewAsked;
        Say(Lang.T("Считаю кадр из середины…"), "busy");
        var folder = Path.Combine(Paths.Session, "preview", asked.ToString(CultureInfo.InvariantCulture));
        var values = Path.Combine(Paths.Session, "preview", $"params-{asked}.json");
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(values)!);
            await File.WriteAllTextAsync(values, view.Values.ForDoor(), new UTF8Encoding(false));
        }
        catch (Exception ex) { Say(Lang.F("предпросмотр не подготовлен: {0}", ex.Message), "bad"); return; }
        var reply = await Door.Call(new[]
        {
            "frame", "--operation", node.Id, "--source", file, "--at", FrameAt.ToString(CultureInfo.InvariantCulture),
            "--out", folder, "--params", values, "--max-width", "1280",
        }, 900_000, cancel.Token);
        try { File.Delete(values); } catch { }
        if (asked != _previewAsked || cancel.IsCancellationRequested) { Forget(folder); return; }
        var line = reply.Out.Split('\n').Select(text => text.Trim()).LastOrDefault(text => text.StartsWith('{'));
        if (line is null)
        {
            Say(Lang.F("предпросмотр не получен: {0}", FirstWords(reply.Err.Length > 0 ? reply.Err : reply.Out)), "bad");
            return;
        }
        try
        {
            using var doc = JsonDocument.Parse(line);
            var told = doc.RootElement;
            if (told.TryGetProperty("error", out var error))
            {
                Say(Lang.F("предпросмотр не получен: {0}", error.GetString() ?? ""), "bad");
                _previewAfter = null;
                ShowPictures();
                return;
            }
            _previewBefore = told.TryGetProperty("before", out var before) ? Load(before.GetProperty("path").GetString() ?? "") : null;
            _previewAfter = told.TryGetProperty("after", out var after) ? Load(after.GetProperty("path").GetString() ?? "") : null;
            _pvFacts.Text = Facts(told);
            var culture = CultureInfo.GetCultureInfo(Lang.Code == "ru" ? "ru-RU" : "en-US");
            Say(Lang.F("Посчитано за {0} с.", told.GetProperty("seconds").GetDouble().ToString("0.0", culture)), "good");
            ShowPictures();
        }
        catch (Exception ex) { Say(Lang.F("предпросмотр не прочитан: {0}", ex.Message), "bad"); }
        finally { Forget(folder); }
    }

    /// <summary>The folder of an answer: thrown away once its pictures are in memory, or once a newer question is asked.</summary>
    static void Forget(string folder)
    {
        try { if (Directory.Exists(folder)) Directory.Delete(folder, true); } catch { }
    }

    /// <summary>A picture read into memory: its file may go at once.</summary>
    static Bitmap? Load(string path)
    {
        try
        {
            if (path.Length == 0 || !File.Exists(path)) return null;
            using var stream = new MemoryStream(File.ReadAllBytes(path));
            return new Bitmap(stream);
        }
        catch { return null; }
    }

    static string FirstWords(string text) => text.Split('\n').Select(line => line.Trim()).LastOrDefault(line => line.Length > 0) ?? "";

    void Say(string text, string tone)
    {
        _pvState.Text = text;
        _pvState.Classes.Set("bad", tone == "bad");
        _pvState.Classes.Set("good", tone == "good");
        _pvDot.IsVisible = tone == "busy";
        _pvDot.Classes.Set("pulse", tone == "busy");
    }

    static readonly Regex NoiseLine = new(@"noise ([\d.]+) / ([\d.]+) / ([\d.]+).*?->\s*(.+)$");

    /// <summary>
    /// The facts under the controls: the video - its size, its rate, the frame shown; the result when its size or rate is
    /// another (an upscale, an interpolation); the noise a denoise preset measured and what it made of it.
    /// </summary>
    static string Facts(JsonElement told)
    {
        var lines = new List<string>();
        static string Side(JsonElement side) =>
            $"{side.GetProperty("width").GetInt32()} × {side.GetProperty("height").GetInt32()}"
            + (side.GetProperty("fps").GetDouble() > 0 ? " · " + side.GetProperty("fps").GetDouble().ToString("0.###", CultureInfo.InvariantCulture) + " " + Lang.T("к/с") : "");
        if (told.TryGetProperty("before", out var before))
            lines.Add(Lang.T("Исходник") + ": " + Side(before) + " · " + Lang.F("кадр {0} из {1}", before.GetProperty("frame").GetInt32() + 1, before.GetProperty("frames").GetInt32()));
        if (told.TryGetProperty("after", out var after) && told.TryGetProperty("before", out var source)
            && (after.GetProperty("width").GetInt32() != source.GetProperty("width").GetInt32()
                || after.GetProperty("frames").GetInt32() != source.GetProperty("frames").GetInt32()))
            lines.Add(Lang.T("Результат") + ": " + Side(after) + " · " + Lang.F("кадров {0}", after.GetProperty("frames").GetInt32()));
        if (told.TryGetProperty("noise", out var noise) && NoiseLine.Match(noise.GetString() ?? "") is { Success: true } measured)
            lines.Add(Lang.T("Шум") + $": Y {measured.Groups[1].Value} · U {measured.Groups[2].Value} · V {measured.Groups[3].Value} → {measured.Groups[4].Value}");
        return string.Join("\n", lines);
    }

    /// <summary>The pictures as the mode asks: before, after, or both side by side - each fitted into its cell.</summary>
    void ShowPictures()
    {
        SizeFrame();
        _pvPictures.Children.Clear();
        _pvPictures.ColumnDefinitions.Clear();
        var shown = _previewMode switch
        {
            "before" => new[] { (_previewBefore, "") },
            "both" => new[] { (_previewBefore, Lang.T("До")), (_previewAfter, Lang.T("После")) },
            _ => new[] { (_previewAfter ?? _previewBefore, "") },
        };
        for (int at = 0; at < shown.Length; at++)
        {
            if (at > 0)
            {
                _pvPictures.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Auto));
                var rule = new Border { Width = 1, Margin = new Thickness((Between - 1) / 2, 0), VerticalAlignment = VerticalAlignment.Stretch };
                rule.Bind(Border.BackgroundProperty, rule.GetResourceObservable("BorderSoft"));
                Grid.SetColumn(rule, _pvPictures.ColumnDefinitions.Count - 1);
                _pvPictures.Children.Add(rule);
            }
            _pvPictures.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            var (picture, caption) = shown[at];
            var cell = new Grid { RowDefinitions = new RowDefinitions("Auto,*") };
            // The caption stands over the middle of its picture.
            if (caption.Length > 0) cell.Children.Add(new TextBlock { Classes = { "factname" }, Text = caption, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 0, 0, 3) });
            if (picture is not null)
            {
                var frame = new Border
                {
                    BorderThickness = new Thickness(1),
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
                    Child = new Image { Source = picture, Stretch = Stretch.Uniform },
                };
                frame.Bind(Border.BorderBrushProperty, frame.GetResourceObservable("BorderSoft"));
                Grid.SetRow(frame, 1);
                cell.Children.Add(frame);
            }
            Grid.SetColumn(cell, _pvPictures.ColumnDefinitions.Count - 1);
            _pvPictures.Children.Add(cell);
        }
    }
}
