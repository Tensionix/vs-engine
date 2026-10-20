using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using AudionVSEngine.Core;

namespace AudionVSEngine.Views;

/// <summary>
/// The additional components the program works with, and the offer to install them now (the owner, 18.10.2026: "нужно
/// всегда при загрузке предупреждать во всплывающем окне, что нужно установить это, это, это и предложить сделать это
/// сразу"). Why the engine is installed apart - a few points; then a block of each component - its sign, its name, the
/// size of its download, what it is for and its files, the type smaller under the name ("Лучше это окно сделать из
/// нескольких буллетов в отдельных блоках, уменьшить кегль после заголовков"); the total; INSTALL: the components are
/// installed one after another, as SETUP installs them. At the start of the window a tick INSTALL LATER stands beside
/// it: ticked, it says where SETUP is and the button becomes UNDERSTOOD ("Если же пользователь нажимает чекбокс
/// «Установить позже», нужно указать, где находится меню"). From SETUP itself CANCEL stands in place of the tick.
/// </summary>
public sealed class SetupDialog : Window
{
    /// <summary>
    /// A component to install: its id (vapoursynth, plugins, ffmpeg, mlrt), its face (a brand mark or a sign), its name, what
    /// it is for, the size of its download ("" - not said) and its files.
    /// </summary>
    public sealed record Item(string Id, Control Face, string Name, string Why, string Size, string Files);

    /// <summary>
    /// The answer: later (INSTALL LATER and UNDERSTOOD, CANCEL, the cross), install now, or OPEN SETUP - the sheet of the
    /// window with every component and its own button.
    /// </summary>
    public enum Answer { Later, Install, Open }

#if DEBUG
    /// <summary>A check that pictures the question: called once it is open; it closes the question itself.</summary>
    public static Func<SetupDialog, Task>? DevShown;
    CheckBox? _tick;
    Button? _open;
    public void DevTick() { if (_tick is not null) _tick.IsChecked = true; }
    public void DevClose() => Close(Answer.Later);
    /// <summary>OPEN SETUP pressed as a hand presses it: false when the question has none (asked from SETUP).</summary>
    public bool DevOpen()
    {
        if (_open is null) return false;
        _open.RaiseEvent(new Avalonia.Interactivity.RoutedEventArgs(Button.ClickEvent));
        return true;
    }
#endif

    /// <summary>The sizes of the type: the head, the name of a block, its text, its small print.</summary>
    const double TypeHead = 15, TypeName = 13.5, TypeText = 12, TypeSmall = 11;

    SetupDialog(Window owner, IReadOnlyList<Item> items, string total, bool later)
    {
        var title = Lang.T("Установка дополнительных компонентов");
        Title = title;
        Width = 660;
        SizeToContent = SizeToContent.Height;
        CanResize = false;
        CanMinimize = false;
        CanMaximize = false;
        ShowInTaskbar = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        // A walk by UI Automation: the question stands where its window does, off the screen, and takes no focus.
        if (Program.Walk)
        {
            ShowActivated = false;
            Opened += (_, _) => Position = new PixelPoint(owner.Position.X + 40, owner.Position.Y + 40);
        }
        Icon = owner.Icon;
        this.Ink(BackgroundProperty, "AppBg").Ink(ForegroundProperty, "TextMain").Ink(FontFamilyProperty, "FontUi");
        FontSize = 13;
        Classes.Set("vault", owner.Classes.Contains("vault"));

        var body = new StackPanel { Spacing = 12 };
        body.Children.Add(new TextBlock { Text = title, FontSize = TypeHead, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap });

        // Why the engine comes apart: a step of the installation, not a fault (the owner, 18.10.2026: "Будет уже звучать не
        // как чего-то недостающее, а именно дополнительное").
        var points = new StackPanel { Spacing = 3 };
        foreach (var point in new[]
                 {
                     "Движок обработки не входит в программу: у VapourSynth, его плагинов, FFmpeg и MLRT свои лицензии.",
                     "Они ставятся отдельно, с сайтов авторов, в папку программы; в Windows ничего не пишется.",
                     "Ход установки виден в терминале окна; СТОП прерывает её.",
                 })
            points.Children.Add(Bullet(Lang.T(point)));
        body.Children.Add(points);

        var list = new StackPanel { Spacing = 6 };
        list.Children.Add(new TextBlock { Classes = { "caption" }, Text = Lang.T("БУДУТ УСТАНОВЛЕНЫ") });
        foreach (var item in items) list.Children.Add(Block(item));
        body.Children.Add(list);
        body.Children.Add(new TextBlock { Text = total, FontSize = TypeText, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap });

        var hint = new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6), Padding = new Thickness(10, 8), IsVisible = false,
            Child = new TextBlock
            {
                FontSize = TypeText, TextWrapping = TextWrapping.Wrap,
                Text = Lang.T("Установить можно в любой момент: кнопка SETUP в шапке окна, справа - рядом с СЕРВИС. В SETUP у каждого компонента своя кнопка УСТАНОВИТЬ, а УСТАНОВИТЬ ВСЁ ставит их по порядку."),
            }.Ink(TextBlock.ForegroundProperty, "AmberInk"),
        }.Ink(Border.BorderBrushProperty, "AmberInk");
        Avalonia.Automation.AutomationProperties.SetAutomationId(hint.Child!, "setup_hint");

        var install = new Button { Name = "SetupInstall", Content = Lang.T("УСТАНОВИТЬ"), Classes = { "run" }, MinWidth = 118, MinHeight = 30 };
        Avalonia.Automation.AutomationProperties.SetAutomationId(install, "setup_install");
        install.Click += (_, _) => Close(Answer.Install);
        var row = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Spacing = 9 };
        var foot = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Margin = new Thickness(0, 2, 0, 0) };
        Grid.SetColumn(row, 1);
        foot.Children.Add(row);
        if (later)
        {
            var close = new Button { Name = "SetupClose", Content = Lang.T("ПОНЯТНО"), MinWidth = 118, MinHeight = 30, IsVisible = false };
            Avalonia.Automation.AutomationProperties.SetAutomationId(close, "setup_close");
            close.Click += (_, _) => Close(Answer.Later);
            // OPEN SETUP: the sheet itself, one press away; in sight whatever the tick says.
            var open = new Button { Name = "SetupOpen", Content = Lang.T("ОТКРЫТЬ SETUP"), MinWidth = 118, MinHeight = 30 };
            Avalonia.Automation.AutomationProperties.SetAutomationId(open, "setup_open");
            open.Click += (_, _) => Close(Answer.Open);
            row.Children.Add(open);
#if DEBUG
            _open = open;
#endif
            var tick = new CheckBox { Content = Lang.T("Установить позже"), VerticalAlignment = VerticalAlignment.Center };
            Avalonia.Automation.AutomationProperties.SetAutomationId(tick, "setup_later");
            tick.IsCheckedChanged += (_, _) =>
            {
                bool wait = tick.IsChecked == true;
                hint.IsVisible = close.IsVisible = wait;
                install.IsVisible = !wait;
                (wait ? (Control)close : install).Focus();
            };
            foot.Children.Add(tick);
            row.Children.Add(close);
#if DEBUG
            _tick = tick;
#endif
        }
        else
        {
            var cancel = new Button { Name = "SetupCancel", Content = Lang.T("ОТМЕНА"), MinWidth = 118, MinHeight = 30, IsCancel = true };
            Avalonia.Automation.AutomationProperties.SetAutomationId(cancel, "setup_cancel");
            cancel.Click += (_, _) => Close(Answer.Later);
            row.Children.Add(cancel);
        }
        row.Children.Add(install);
        body.Children.Add(hint);
        body.Children.Add(foot);
        Opened += (_, _) => install.Focus();
#if DEBUG
        Opened += async (_, _) => { if (DevShown is { } shown) { DevShown = null; await shown(this); } };
#endif

        Content = new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8), Margin = new Thickness(10), Padding = new Thickness(18, 15),
            Child = body,
        }.Ink(Border.BackgroundProperty, "PanelBg").Ink(Border.BorderBrushProperty, "BorderSoft");
    }

    /// <summary>A point: the dot at the left, the text wrapping under itself, not under the dot.</summary>
    static Control Bullet(string text)
    {
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("14,*") };
        grid.Children.Add(new TextBlock { Text = "•", FontSize = TypeText }.Ink(TextBlock.ForegroundProperty, "TextMuted"));
        var said = new TextBlock { Text = text, FontSize = TypeText, TextWrapping = TextWrapping.Wrap };
        Grid.SetColumn(said, 1);
        grid.Children.Add(said);
        return grid;
    }

    /// <summary>
    /// A component in a block of its own, a step off the ground of the question: its face and name, the size at the right;
    /// what it is for under them, smaller; its files under that, smaller and quieter.
    /// </summary>
    static Control Block(Item item)
    {
        item.Face.VerticalAlignment = VerticalAlignment.Center;
        item.Face.Margin = new Thickness(0, 0, 8, 0);
        var name = new TextBlock { Text = item.Name, FontSize = TypeName, FontWeight = FontWeight.SemiBold, VerticalAlignment = VerticalAlignment.Center };
        Avalonia.Automation.AutomationProperties.SetAutomationId(name, "setup_item_" + item.Id);
        var size = new TextBlock { Text = item.Size, FontSize = TypeText, VerticalAlignment = VerticalAlignment.Center }.Ink(TextBlock.ForegroundProperty, "TextMuted");
        var head = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto") };
        head.Children.Add(item.Face);
        Grid.SetColumn(name, 1);
        head.Children.Add(name);
        Grid.SetColumn(size, 2);
        head.Children.Add(size);
        var why = new TextBlock { Text = item.Why, FontSize = TypeText, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0) };
        var files = new TextBlock { Text = item.Files, FontSize = TypeSmall, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 3, 0, 0) }
            .Ink(TextBlock.ForegroundProperty, "TextMuted");
        return new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6), Padding = new Thickness(10, 8),
            Child = new StackPanel { Children = { head, why, files } },
        }.Ink(Border.BackgroundProperty, "SwitchBg").Ink(Border.BorderBrushProperty, "BorderSoft");
    }

    /// <summary>
    /// Install now, later, or open SETUP. <paramref name="later"/>: the start of the window - the tick INSTALL LATER and
    /// OPEN SETUP stand beside INSTALL; without it (asked from SETUP) - CANCEL.
    /// </summary>
    public static Task<Answer> Ask(Window owner, IReadOnlyList<Item> items, string total, bool later) =>
        new SetupDialog(owner, items, total, later).ShowDialog<Answer>(owner);
}
