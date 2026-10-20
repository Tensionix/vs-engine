using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Layout;
using Avalonia.Threading;
using AudionVSEngine.Core;
using AudionVSEngine.Views;
using Page = AudionVSEngine.Core.Page;

namespace AudionVSEngine;

/// <summary>
/// The pages of the window: a preset of a palette, or an operation of PROFILES, with a form of its own. A page is built
/// when it is first opened and then stays in the window, hidden while another is in sight; its form is held by the form
/// server, and what the page held is kept in config\window_settings.json and opened so at the next start (until 3.0.0
/// the values were lost when the window closed). A page whose form changed shape is built again when it is in sight.
/// </summary>
public partial class MainWindow
{
    sealed class PageView
    {
        public required Page Page;
        public required Values Values;
        public required Form Form;
        public required ScrollViewer Root;
        public required StackPanel Cards;
        /// <summary>The button that runs the operation of the page: the one filled button of the window.</summary>
        public Button? Run;
        /// <summary>COMMAND beside RUN: the commands of vspipe and FFmpeg the run would start, said in the journal, nothing run.</summary>
        public Button? Dry;
        /// <summary>The operations the page runs with its own values: SAVE AS PROFILE.</summary>
        public List<Button> Own = new();
        /// <summary>The page is to be built before it is shown: never built yet, or what it shows is out of date.</summary>
        public bool Stale = true;
        /// <summary>The form server holds this page.</summary>
        public bool Opened;
    }

    readonly Dictionary<string, PageView> _views = new();
    PageView? _view;
    /// <summary>The form server was started anew: every page asks for its form again before it is shown.</summary>
    bool _reopen;

    PageView ViewOf(Page page)
    {
        if (_views.TryGetValue(page.Key, out var known)) return known;
        var cards = new StackPanel { Margin = new Thickness(10, 10, 10, 4), Spacing = 8 };
        var root = new ScrollViewer
        {
            Content = cards, IsVisible = false,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
        PageView? view = null;
        var values = new Values(_forms, page);
        values.Failed += trouble =>
        {
            AppendLines(new[] { "[GUI] " + Lang.F("форма не ответила: {0}", trouble) });
            SetStatus("Форма не ответила: причина в терминале.");
        };
        var form = new Form(values, () => Outdated(view!)) { Grown = CentreWords };
        view = new PageView { Page = page, Values = values, Form = form, Root = root, Cards = cards };
        PageHost.Children.Add(root);
        return _views[page.Key] = view;
    }

    /// <summary>The form of a page has to change. The page in sight is built again at once; a hidden one, when it is next opened.</summary>
    void Outdated(PageView view)
    {
        view.Stale = true;
        if (ReferenceEquals(view, _view)) RebuildSoon();
    }

    void SelectPage(Page page)
    {
        Remember(_view);
        _page = page;
        if (page.Section is { } section) _lastPage[section.Id] = page.Id;
        foreach (var tab in PageTabs()) tab.IsChecked = (string?)tab.Tag == page.Id;
        if (_reopen)
        {
            // The server that held the forms is a new one: what every page held goes to it again.
            _reopen = false;
            foreach (var other in _views.Values.Where(other => other.Opened)) { Remember(other); other.Opened = false; other.Stale = true; }
        }
        var view = ViewOf(page);
        _view = view;
        if (!view.Opened)
        {
            view.Opened = view.Values.Open(_settings.Forms.TryGetValue(page.Key, out var held) ? held : null);
            view.Stale = true;
        }
        else
        {
            // Another page may have set the machine - where BM3D runs, the cards of the encoder - since this one was in sight.
            view.Values.Refresh();
        }
        if (view.Stale) Build(view, whole: false);
        Show(view);
    }

    /// <summary>The switches of the pages of the section: one band, or the bands of its groups.</summary>
    IEnumerable<ToggleButton> PageTabs() => PageRow.Children.OfType<ToggleButton>()
        .Concat(PageGroups.Children.OfType<Grid>().SelectMany(cell => cell.Children.OfType<EvenRow>()).SelectMany(row => row.Children.OfType<ToggleButton>()));

    /// <summary>What a page holds goes into the settings: it opens so at the next start.</summary>
    void Remember(PageView? view)
    {
        if (view is not { Opened: true }) return;
        var held = view.Values.Remember();
        if (held.Count > 0) _settings.Forms[view.Page.Key] = held;
        else _settings.Forms.Remove(view.Page.Key);
    }

    /// <summary>The name of a page with its place: "ТОЧНОСТЬ → Мягкий шумодав".</summary>
    static string PathName(Page page) => page.Section is { } section ? $"{Upper(section.Name)} → {page.Name}" : page.Name;

    /// <summary>The page comes into sight: the others hide, the bar over the form takes its name and its buttons.</summary>
    void Show(PageView view)
    {
        CardsNote.IsVisible = false;
        foreach (var other in _views.Values) other.Root.IsVisible = ReferenceEquals(other, view);
        ActionButtons.Children.Clear();
        foreach (var own in view.Own) ActionButtons.Children.Add(own);
        if (view.Dry is not null) ActionButtons.Children.Add(view.Dry);
        if (view.Run is not null) ActionButtons.Children.Add(view.Run);
        ActionTitle.Text = PathName(view.Page);
        ToolTip.SetTip(ActionTitle, view.Page.Node.About);
        ActionReset.IsVisible = view.Page.Node.Fields.Count > 0;
        ActionBar.IsVisible = true;
        PageBar.IsVisible = _section is { Pages.Count: > 1 };
        ShowEngine();
        ApplyBusy();
        CentreWords();
    }

    bool _rebuildPosted;

    /// <summary>The page in sight is built again after the press that asked for it has been handled, once for any number of changes.</summary>
    void RebuildSoon()
    {
        if (_rebuildPosted) return;
        _rebuildPosted = true;
        Dispatcher.UIThread.Post(() =>
        {
            _rebuildPosted = false;
            if (_view is not { } view) return;
            var offset = view.Root.Offset;
            Build(view, whole: true);
            Show(view);
            Dispatcher.UIThread.Post(() => view.Root.Offset = offset, DispatcherPriority.Loaded);
        });
    }

    /// <summary>"Back to the defaults": the form of the page goes back to how it opens; the machine stays.</summary>
    void ResetPage(PageView view)
    {
        view.Values.Reset();
        _settings.Forms.Remove(view.Page.Key);
        Outdated(view);
    }

    /// <summary>Every page is out of date: the theme or a font changed. The one in sight is built again now.</summary>
    void OutdateAll()
    {
        foreach (var view in _views.Values) view.Stale = true;
        if (_view is not null) RebuildSoon();
    }

    /// <summary>Every page is thrown away: the language changed, and with it every word a page was built of.</summary>
    void ForgetPages()
    {
        foreach (var view in _views.Values) { Remember(view); view.Form.Detach(); }
        _views.Clear();
        _view = null;
        PageHost.Children.Clear();
        ActionButtons.Children.Clear();
    }

    // ------------------------------------------------------------ the form of a page

    /// <summary>The pages whose fields of an unknown kind the journal has named since the start.</summary>
    readonly HashSet<string> _toldUnknown = new();

    void Build(PageView view, bool whole)
    {
        var page = view.Page;
        view.Form.Forget();
        view.Form.Lazy = !whole;
        view.Cards.Children.Clear();
        view.Run = RunButton(page);
        view.Dry = DryButton(page);
        view.Own = OwnButtons(view);
        // A form without a field in sight says what its run does, where the fields would stand.
        if (view.Values.Blocks.Count == 0)
            view.Cards.Children.Add(new TextBlock { Classes = { "note" }, Text = page.Node.About, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Margin = new Thickness(14, 12) });
        else
        {
            // What the preset does, a line over its form: its parameters are read with it in mind.
            if (page.Node.About.Length > 0)
                view.Cards.Children.Add(new TextBlock { Classes = { "note" }, Text = page.Node.About, TextWrapping = Avalonia.Media.TextWrapping.Wrap, Margin = new Thickness(4, 0, 4, 2) });
            view.Cards.Children.Add(view.Form.Build(page.Node));
        }
        if (view.Form.Unknown.Count > 0)
        {
            // Said once a start for a page: a page is built again at every visit, and the line came every time.
            var told = string.Join("; ", view.Form.Unknown);
            if (_toldUnknown.Add(page.Key + " " + told)) AppendLines(new[] { Lang.F("[GUI] поля неизвестного вида не показаны: {0}", told) });
            view.Form.Unknown.Clear();
        }
        if (Lang.Code != "ru") Lang.Walk(view.Cards);
        view.Stale = false;
        view.Form.Lazy = true;
    }

    /// <summary>
    /// Every word of a button, a chip and a badge to the vertical middle of its control, on whole pixels
    /// (Views\PixelGrid.cs): asked once the part just built is in the window.
    /// </summary>
    void CentreWords() => Dispatcher.UIThread.Post(() => PixelGrid.Adopt(this), DispatcherPriority.Loaded);

    /// <summary>
    /// The run of a page: RUN, filled with the accent, at the right of the bar - the one filled button of the window
    /// (the owner, 10.10.2026: "Их нужно сделать с правой стороны, полностью залитыми цветом акцента с белым шрифтом,
    /// без иконки. Без описания. Всё описание в тултипе").
    /// </summary>
    Button RunButton(Page page)
    {
        var button = new Button
        {
            Tag = page.Node, Classes = { "step", "fill" }, Content = new TextBlock { Text = Upper(Lang.T("Запустить")) },
            Height = 30, MinHeight = 30, Margin = new Thickness(4, 0, 0, 0),
        };
        Avalonia.Automation.AutomationProperties.SetAutomationId(button, "run_" + page.Node.Id);
        ToolTip.SetTip(button, PathName(page) + (page.Node.About.Length > 0 ? "\n" + page.Node.About : ""));
        button.Click += (_, _) => Press(page.Node, page);
        return button;
    }

    /// <summary>
    /// COMMAND, outlined, before RUN: the run of the page with --dry-run - the engine says in the journal the commands of
    /// vspipe and FFmpeg it would start for every file of the Source and starts none. Only an operation that can (a preset,
    /// a profile) has it: another would run for real.
    /// </summary>
    Button? DryButton(Page page)
    {
        if (!page.Node.DryRun) return null;
        var button = new Button
        {
            Classes = { "step" }, Height = 30, MinHeight = 30, Margin = new Thickness(4, 0, 0, 0),
            Content = new StackPanel
            {
                Orientation = Orientation.Horizontal, Spacing = 6,
                Children = { Icons.Sign("terminal"), new TextBlock { Text = Lang.T("КОМАНДА"), VerticalAlignment = VerticalAlignment.Center } },
            },
        };
        Avalonia.Automation.AutomationProperties.SetAutomationId(button, "dry_" + page.Node.Id);
        ToolTip.SetTip(button, Lang.T("Показать в терминале команды vspipe и FFmpeg, которые запустит операция с этими значениями, для каждого файла Источника, ничего не запуская."));
        button.Click += (_, _) => Press(page.Node, page, dry: true);
        return button;
    }

    /// <summary>The operations of the layout a page of this section runs with its own values (`buttons`): SAVE AS PROFILE.</summary>
    List<Button> OwnButtons(PageView view)
    {
        var buttons = new List<Button>();
        if (_told is not { } told || view.Page.Section is not { } section) return buttons;
        foreach (var own in told.Layout.Buttons.Where(button => button.Sections.Count == 0 || button.Sections.Contains(section.Id)))
        {
            if (told.Find(own.Op) is not { } node) continue;
            var button = new Button
            {
                Classes = { "step" }, Height = 30, MinHeight = 30, Margin = new Thickness(4, 0, 0, 0),
                Content = new StackPanel
                {
                    Orientation = Orientation.Horizontal, Spacing = 6,
                    Children = { Icons.Sign(own.Icon.Length > 0 ? own.Icon : "play"), new TextBlock { Text = Upper(node.Name), VerticalAlignment = VerticalAlignment.Center } },
                },
            };
            Avalonia.Automation.AutomationProperties.SetAutomationId(button, "own_" + node.Id);
            ToolTip.SetTip(button, TipOf(node));
            button.Click += (_, _) => RunOwn(node, view);
            buttons.Add(button);
        }
        return buttons;
    }
}
