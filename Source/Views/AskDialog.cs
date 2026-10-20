using System;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Layout;
using Avalonia.Media;
using AudionVSEngine.Core;

namespace AudionVSEngine.Views;

/// <summary>
/// A question of the window, in the look of the window: a head, the lines that say everything
/// that decides the outcome, and two buttons - CANCEL and YES, the right one in the tone of what
/// it starts - or one UNDERSTOOD; or a value asked for - a box under the lines, CANCEL and the word of
/// what it does (SAVE). The shape of the confirmation of Audion Build Publisher (Views\Dialog.axaml there).
/// </summary>
public sealed class AskDialog : Window
{
#if DEBUG
    /// <summary>A check of the window answers the questions itself: the title and the text come, the answer goes back.</summary>
    public static Func<string, string, bool, bool>? DevAnswer;
    /// <summary>A check that wants the question on the screen: it is shown and answered after so many milliseconds.</summary>
    public static (int Milliseconds, bool Answer, Action<AskDialog>? Shown)? DevShow;
#endif

    // "Root: E:\Release" - a name and what it is: the name is written quieter than its value.
    static readonly Regex Pair = new(@"^(?<key>[^:]{1,48}): (?<value>.+)$", RegexOptions.CultureInvariant);

    /// <summary>The box of a value asked for; null - the dialog asks no value.</summary>
    TextBox? _input;

    AskDialog(Window owner, string title, string message, bool yesNo, string tone, string? value = null, string yes = "ДА")
    {
        // What a question says comes in Russian and is shown in the language of the window - the
        // title, each line by itself (a line with a number or a path is a template of the
        // dictionary), the buttons. A check finds the buttons by their names, not by their words.
        title = Lang.T(title);
        Title = title;
        Width = 580;
        SizeToContent = SizeToContent.Height;
        CanResize = false;
        CanMinimize = false;
        CanMaximize = false;
        ShowInTaskbar = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        // A walk by UI Automation: the question stands where its window does, off the screen, and takes
        // no focus. Placed once it is open: a place set before is not kept (MainWindow.OffScreen).
        if (Program.Walk)
        {
            ShowActivated = false;
            Opened += (_, _) => Position = new PixelPoint(owner.Position.X + 40, owner.Position.Y + 40);
        }
        Icon = owner.Icon;
        this.Ink(BackgroundProperty, "AppBg").Ink(ForegroundProperty, "TextMain").Ink(FontFamilyProperty, "FontUi");
        FontSize = 13;
        // The buttons of a run wear their colour in the text when the theme of the window says so.
        Classes.Set("vault", owner.Classes.Contains("vault"));

        var lines = new StackPanel();
        foreach (var said in message.Replace("\r\n", "\n").Split('\n'))
        {
            var line = Lang.T(said);
            var block = new TextBlock { TextWrapping = TextWrapping.Wrap, Classes = { "plain" } };
            var pair = Pair.Match(line);
            if (pair.Success && !pair.Groups["key"].Value.Contains(". ", StringComparison.Ordinal))
            {
                block.Inlines = new InlineCollection
                {
                    new Run(pair.Groups["key"].Value + ": ") { Foreground = App.Ink("TextMuted") },
                    new Run(pair.Groups["value"].Value),
                };
            }
            else block.Text = line.Length == 0 ? " " : line;
            lines.Children.Add(block);
        }

        if (value is not null)
        {
            _input = new TextBox { Name = "AskValue", Text = value, Classes = { "masks" }, MinHeight = 26, Padding = new Thickness(8, 2), Margin = new Thickness(0, 12, 0, 0) };
            Avalonia.Automation.AutomationProperties.SetAutomationId(_input, "ask_value");
            lines.Children.Add(_input);
        }

        var row = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 18, 0, 0) };
        Button Make(string name, string caption, bool answer, double right)
        {
            var button = new Button { Name = name, Content = Lang.T(caption), MinWidth = 118, MinHeight = 30, Margin = new Thickness(0, 0, right, 0) };
            button.Click += (_, _) => Close(answer);
            row.Children.Add(button);
            return button;
        }
        Button first;
        if (yesNo)
        {
            // Enter is nobody's "yes": what a question starts is started by a press of YES.
            first = Make("AskCancel", "ОТМЕНА", false, 9);
            first.IsCancel = true;
            var yesButton = Make("AskYes", yes, true, 0);
            if (tone.Length > 0) yesButton.Classes.Add(tone);
            // A value is taken with Enter in its box, as a press of the word of what it does.
            if (_input is not null) _input.KeyDown += (_, e) => { if (e.Key == Avalonia.Input.Key.Enter) { e.Handled = true; Close(true); } };
        }
        else
        {
            first = Make("AskOk", "ПОНЯТНО", true, 0);
            first.IsDefault = true;
            first.IsCancel = true;
        }
        Opened += (_, _) => { if (_input is not null) { _input.Focus(); _input.SelectAll(); } else first.Focus(); };

        var head = new TextBlock { Text = title, FontSize = 15, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12) };
        Content = new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8), Margin = new Thickness(10), Padding = new Thickness(18, 15),
            Child = new StackPanel { Children = { head, lines, row } },
        }.Ink(Border.BackgroundProperty, "PanelBg").Ink(Border.BorderBrushProperty, "BorderSoft");
    }

    /// <summary>
    /// YES or CANCEL: true on YES, false on CANCEL and on the cross. <paramref name="tone"/>: the
    /// class the button YES wears - "run" for what builds, "warn" for what removes - or none.
    /// </summary>
    public static Task<bool> YesNo(Window owner, string title, string message, string tone = "") => Show(owner, title, message, true, tone);

    /// <summary>A word to the person, with one button.</summary>
    public static Task Ok(Window owner, string title, string message) => Show(owner, title, message, false, "");

    /// <summary>
    /// A value asked for: the lines, a box holding <paramref name="value"/>, CANCEL and <paramref name="yes"/>. The text of the
    /// box on <paramref name="yes"/>, trimmed; null on CANCEL and on the cross.
    /// </summary>
    public static async Task<string?> Value(Window owner, string title, string message, string value, string yes)
    {
#if DEBUG
        if (DevAnswer is { } answer) return answer(title, message, true) ? value : null;
#endif
        var dialog = new AskDialog(owner, title, message, true, "", value, yes);
        return await dialog.ShowDialog<bool>(owner) ? (dialog._input?.Text ?? "").Trim() : null;
    }

    static async Task<bool> Show(Window owner, string title, string message, bool yesNo, string tone)
    {
#if DEBUG
        if (DevShow is { } show)
        {
            DevShow = null;
            var shown = new AskDialog(owner, title, message, yesNo, tone);
            shown.Opened += async (_, _) =>
            {
                await Task.Delay(show.Milliseconds);
                show.Shown?.Invoke(shown);
                shown.Close(show.Answer);
            };
            return await shown.ShowDialog<bool>(owner);
        }
        if (DevAnswer is { } answer) return answer(title, message, yesNo);
#endif
        return await new AskDialog(owner, title, message, yesNo, tone).ShowDialog<bool>(owner);
    }
}
