using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using AudionVSEngine.Core;

namespace AudionVSEngine.Views;

/// <summary>
/// The form of a page, drawn as the form server holds it (Core\Values.cs): the blocks it names, the fields in sight in
/// them, the choices with those switched off. The form keeps nothing itself and decides nothing: a control used is a
/// question to the server, and its answer repaints the controls - or, when what is in sight changed, builds the form
/// again. A choice is a row of switches, never a drop-down list; a number is a slider in a dark chip with its box beside
/// it; a choice of cards (the codecs of ENCODING) is a card for each choice with the fields shown for it inside.
/// </summary>
public sealed class Form
{
    readonly Values _values;
    /// <summary>What a change of what is in sight asks for: the form is built again.</summary>
    readonly Action _rebuild;

    /// <summary>What repaints the controls of a field, by the id of the field: a form built now, gone at the next build.</summary>
    readonly Dictionary<string, List<Action>> _cells = new();

    /// <summary>Kinds of field met while building that the form cannot draw.</summary>
    public HashSet<string> Unknown { get; } = new();

    /// <summary>The kinds this form draws; anything else is said in the journal, not left as an empty place.</summary>
    static readonly HashSet<string> Drawn = new() { "radio", "select", "checkbox", "number", "int", "integer", "float", "text" };

    public Form(Values values, Action rebuild)
    {
        _values = values;
        _rebuild = rebuild;
        _values.Reshaped += _reshaped = () => _rebuild();
        _values.Changed += _heard = id =>
        {
            if (!_cells.TryGetValue(id, out var repaint)) return;
            foreach (var action in repaint.ToArray()) action();
        };
    }

    readonly Action<string> _heard;
    readonly Action _reshaped;

    /// <summary>The page is thrown away - the language changed: this form stops hearing its values.</summary>
    public void Detach()
    {
        _values.Changed -= _heard;
        _values.Reshaped -= _reshaped;
    }

    /// <summary>A new build begins: the controls of the last one are forgotten.</summary>
    public void Forget() => _cells.Clear();

    /// <summary>Kept for the shape of the shell: the form of a preset is short and is built whole.</summary>
    public bool Lazy { get; set; } = true;

    /// <summary>Raised when a part built later has joined the form: its words want centring too.</summary>
    public Action? Grown { get; set; }

    void Watch(Field field, Action repaint)
    {
        if (!_cells.TryGetValue(field.Id, out var list)) _cells[field.Id] = list = new List<Action>();
        list.Add(repaint);
        repaint();
    }

    static string Upper(string text) => text.ToUpper(CultureInfo.CurrentCulture);

    // ------------------------------------------------------------ the form

    /// <summary>The fields in sight, block by block, in the order the server names the blocks: the usual ones, then the rare.</summary>
    public Control Build(Node node)
    {
        var host = new StackPanel { Spacing = 6 };
        // The names of the fields of every block take one width: the controls begin on one line.
        Grid.SetIsSharedSizeScope(host, true);
        // A choice of cards holds the fields shown for its choices: they are drawn in its cards, not on their own.
        var carded = node.Fields.Where(field => field.Style == "cards")
            .SelectMany(cards => node.Fields.Where(field => field.ShownFor(cards.Id).Count > 0)).Select(field => field.Id).ToHashSet();
        bool rareHeaded = false;
        foreach (var block in _values.Blocks)
        {
            var fields = block.Fields.Select(node.Field).OfType<Field>().Where(field => !carded.Contains(field.Id)).ToList();
            if (fields.Count == 0) continue;
            if (block.Advanced && !rareHeaded)
            {
                // The rare fields stay in sight, under their heading with a rule (the owner, 10.10.2026: "Оставь Дополнительно и разделитель").
                host.Children.Add(Rule(Lang.T("Дополнительно")));
                rareHeaded = true;
            }
            var body = new StackPanel();
            WrapPanel? flags = null;
            var lines = new List<Control>();
            void Lines()
            {
                if (lines.Count > 0) body.Children.Add(TwoColumns(lines.ToList()));
                lines.Clear();
            }
            for (int i = 0; i < fields.Count; i++)
            {
                var field = fields[i];
                if (!Drawn.Contains(field.Kind)) { Unknown.Add($"{field.Id}: {field.Kind}"); continue; }
                if (field.Style == "cards")
                {
                    flags = null;
                    Lines();
                    body.Children.Add(Cards(field, node));
                    continue;
                }
                if (field.Kind == "checkbox")
                {
                    Lines();
                    // Flags that follow one another stand in one row.
                    if (flags is null) body.Children.Add(flags = new WrapPanel { Orientation = Orientation.Horizontal });
                    flags.Children.Add(Flag(field));
                    continue;
                }
                flags = null;
                if (field.Pair.Length > 0)
                {
                    // The fields of a pair stand on one line under the name of the pair.
                    var pair = fields.Skip(i).TakeWhile(other => other.Pair == field.Pair).ToList();
                    lines.Add(PairLine(pair));
                    i += pair.Count - 1;
                    continue;
                }
                bool alone = fields.Count == 1 && string.Equals(field.Name, GroupName(block.Name), StringComparison.CurrentCultureIgnoreCase);
                lines.Add(alone ? Bare(field) : Cell(field));
            }
            Lines();
            if (body.Children.Count == 0) continue;
            var name = GroupName(block.Name);
            if (name.Length > 0) body.Children.Insert(0, new TextBlock { Classes = { "grp" }, Text = Upper(name) });
            host.Children.Add(new Border { Classes = { "grp" }, Child = Striped(body, block.Name) });
        }
        return host;
    }

    /// <summary>The heading of the rare fields: a name and a rule across the form.</summary>
    static Control Rule(string name)
    {
        var line = new Border { Height = 1, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 1, 0, 0) }.Ink(Border.BackgroundProperty, "SepInk");
        var title = new TextBlock { Classes = { "grp" }, Text = Upper(name), VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(2, 6, 0, 0) };
        Grid.SetColumn(line, 1);
        return new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), Children = { title, line } };
    }

    /// <summary>
    /// Lines of fields in two columns with a rule between them when the form is wide enough (the owner of Audion Get Tools,
    /// 10.10.2026: "в две колонки, разделённые палкой"), one under another otherwise.
    /// </summary>
    static Control TwoColumns(List<Control> lines)
    {
        var left = new StackPanel();
        if (lines.Count < 2)
        {
            foreach (var line in lines) left.Children.Add(line);
            return left;
        }
        int half = (lines.Count + 1) / 2;
        var right = new StackPanel();
        for (int i = 0; i < lines.Count; i++) (i < half ? left : right).Children.Add(lines[i]);
        var rule = new Border { Width = 1, Margin = new Thickness(0, 1, 0, 5), HorizontalAlignment = HorizontalAlignment.Center }.Ink(Border.BackgroundProperty, "SepInk");
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,21,*"), RowDefinitions = new RowDefinitions("Auto,Auto") };
        Grid.SetColumn(rule, 1);
        grid.Children.Add(left);
        grid.Children.Add(rule);
        grid.Children.Add(right);
        bool? wide = null;
        void Fit(double width)
        {
            bool now = width >= TwoColumnsFrom;
            if (wide == now) return;
            wide = now;
            rule.IsVisible = now;
            Grid.SetColumn(right, now ? 2 : 0);
            Grid.SetRow(right, now ? 0 : 1);
            Grid.SetColumnSpan(left, now ? 1 : 3);
            Grid.SetColumnSpan(right, now ? 1 : 3);
        }
        Fit(TwoColumnsFrom);
        grid.SizeChanged += (_, e) => Fit(e.NewSize.Width);
        return grid;
    }

    /// <summary>The width from which a block holds two columns of fields: a name and its control, twice.</summary>
    const double TwoColumnsFrom = 760;

    /// <summary>The name of a block of the form; "" - the block needs none.</summary>
    public static string GroupName(string block) => block switch
    {
        "parameters" => Lang.T("Параметры"),
        "processing" => Lang.T("Обработка"),
        "encoding" => Lang.T("Кодирование"),
        "run" => Lang.T("Запуск"),
        "" => "",
        _ => char.ToUpperInvariant(block[0]) + block[1..].Replace('_', ' '),
    };

    /// <summary>A control with the name of its field before it, the names of a block on one width.</summary>
    static Control Named(string name, string tip, Control control)
    {
        if (name.Length == 0) return control;
        var line = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), Margin = new Thickness(0, 0, 0, 2) };
        line.ColumnDefinitions[0].SharedSizeGroup = "FieldName";
        var label = new TextBlock { Classes = { "fieldname" }, Text = name, Margin = new Thickness(1, 0, 14, 4), VerticalAlignment = VerticalAlignment.Center, MaxWidth = 210, TextWrapping = TextWrapping.Wrap };
        if (tip.Length > 0) ToolTip.SetTip(label, tip);
        line.Children.Add(label);
        Grid.SetColumn(control, 1);
        line.Children.Add(control);
        return line;
    }

    /// <summary>A field without its name before it: the head of its block says it.</summary>
    Control Bare(Field field)
    {
        var control = Cell(new Field { Id = field.Id, Kind = field.Kind, Action = field.Action, Label = "", LabelRu = "" }, field);
        if (field.Tip.Length > 0) ToolTip.SetTip(control, field.Tip);
        return control;
    }

    Control Cell(Field field) => Cell(field, field);

    /// <summary>The control of <paramref name="field"/> under the name of <paramref name="named"/>.</summary>
    Control Cell(Field named, Field field)
    {
        Control control = field.Kind switch
        {
            "radio" or "select" => Choice(field),
            "number" or "int" or "integer" or "float" => NumberBox(field),
            _ => TextBox(field),
        };
        return Named(named.Name, field.Tip, control);
    }

    /// <summary>The fields of a pair on one line under its name: Quants - quant 1, quant 2.</summary>
    Control PairLine(List<Field> pair)
    {
        var row = new Grid();
        for (int i = 0; i < pair.Count; i++)
        {
            if (i > 0) row.ColumnDefinitions.Add(new ColumnDefinition(new GridLength(10)));
            row.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            var box = pair[i].Kind is "radio" or "select" ? Choice(pair[i]) : NumberBox(pair[i]);
            Grid.SetColumn(box, row.ColumnDefinitions.Count - 1);
            row.Children.Add(box);
        }
        var name = pair[0].PairName.Length > 0 ? pair[0].PairName : pair[0].Name;
        return Named(name, string.Join("\n\n", pair.Select(field => field.Name + ": " + field.Tip)), row);
    }

    // ------------------------------------------------------------ controls

    static readonly Geometry Tick = Geometry.Parse("M 1.5,5 L 4,7.5 L 8.5,2.5");

    static Border TickBox() => new()
    {
        Classes = { "tickbox" },
        Child = new Avalonia.Controls.Shapes.Path { Classes = { "tick" }, Data = Tick },
    };

    static Control Faced(string text) => new StackPanel
    {
        Orientation = Orientation.Horizontal, Spacing = 7,
        Children = { TickBox(), new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center } },
    };

    ToggleButton Flag(Field field)
    {
        var flag = new ToggleButton { Classes = { "switch" }, Content = Faced(field.Name), Margin = new Thickness(0, 0, 6, 6) };
        Avalonia.Automation.AutomationProperties.SetAutomationId(flag, "field_" + field.Id);
        if (field.Tip.Length > 0) ToolTip.SetTip(flag, field.Tip);
        flag.Click += (_, _) => _values.Set(field, flag.IsChecked == true ? "true" : "false");
        Watch(field, () => flag.IsChecked = _values.IsOn(field));
        return flag;
    }

    /// <summary>The choices of a field: as the server holds them, or - for a field not in sight - those of the manifest.</summary>
    IReadOnlyList<(string Key, bool Off, string Name, Option? Option)> ChoicesOf(Field field, bool asHeld = true)
    {
        var held = asHeld ? _values.ChoicesOf(field) : Array.Empty<Choice>();
        if (held.Count == 0) return field.Options.Select(option => (option.Key, false, option.Name, (Option?)option)).ToList();
        return held.Select(choice =>
        {
            var option = field.OptionOf(choice.Key);
            var name = option?.Name ?? (choice.Label.Length > 0 ? choice.Label : choice.Key);
            return (choice.Key, choice.Off, name, option);
        }).ToList();
    }

    /// <summary>
    /// A choice of a few: a row of switches, one of them on, which goes into an even grid when it does not fit its line
    /// (EvenWrap). A choice that is switched off stays in its place, greyed, and says why in its tooltip.
    /// <paramref name="before"/> runs before a press is told to the server: a card makes its codec the chosen one first.
    /// </summary>
    Control Choice(Field field, bool asHeld = true, Action? before = null)
    {
        var row = new EvenWrap();
        var buttons = new List<(ToggleButton Button, string Key)>();
        foreach (var (key, off, name, option) in ChoicesOf(field, asHeld))
        {
            // The name in a text of its own: given as the content itself, its first "_" would be taken for an access key and
            // not drawn ("archival_master" read "archivalmaster").
            var button = new ToggleButton
            {
                Classes = { "switch" }, Content = new TextBlock { Text = name }, Margin = new Thickness(0, 0, 4, 4), IsEnabled = !off,
                HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Center,
            };
            if (option is not null) ChoiceTones.Wear(button, option.ToneInUse);
            Avalonia.Automation.AutomationProperties.SetAutomationId(button, $"field_{field.Id}_{key}");
            var tip = option is { Tip.Length: > 0 } ? option.Tip : field.Tip;
            if (off && _values.WhyOff(field, key) is { Length: > 0 } why) tip = tip.Length > 0 ? why + "\n\n" + tip : why;
            if (tip.Length > 0) ToolTip.SetTip(button, tip);
            // A greyed switch still says what it is and why it is off.
            if (off) ToolTip.SetShowOnDisabled(button, true);
            button.Click += (_, _) =>
            {
                before?.Invoke();
                _values.Set(field, key);
                // A press on the chosen one must not switch it off: one of the row is always on.
                button.IsChecked = _values.Get(field) == key;
            };
            buttons.Add((button, key));
            row.Children.Add(button);
        }
        Watch(field, () =>
        {
            var current = _values.Get(field);
            foreach (var (button, key) in buttons) button.IsChecked = key == current;
        });
        return row;
    }

    /// <summary>
    /// A choice of cards: every choice of the field is a card with its name at the top and inside it the fields shown for
    /// it (the owner on the codecs of the former window: four cards x264 / x265 / ProRes / DNxHR, the ones not chosen
    /// shaded). A press on a card, or on a switch inside one, makes its choice the chosen one.
    /// </summary>
    Control Cards(Field cards, Node node)
    {
        var grid = new Grid();
        var faces = new List<(Border Card, Border Halo, ToggleButton Head, Control Body, string Key)>();
        foreach (var (key, _, name, option) in ChoicesOf(cards, asHeld: false))
        {
            if (grid.ColumnDefinitions.Count > 0) grid.ColumnDefinitions.Add(new ColumnDefinition(new GridLength(6)));
            grid.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
            var head = new ToggleButton
            {
                Classes = { "switch", "cardhead" }, Content = new TextBlock { Text = name }, HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 0, 0, 6),
            };
            if (option is not null) ChoiceTones.Wear(head, option.ToneInUse);
            Avalonia.Automation.AutomationProperties.SetAutomationId(head, $"field_{cards.Id}_{key}");
            var tip = option is { Tip.Length: > 0 } ? option.Tip : cards.Tip;
            if (tip.Length > 0) ToolTip.SetTip(head, tip);
            void Choose() { if (_values.Get(cards) != key) _values.Set(cards, key); }
            head.Click += (_, _) =>
            {
                Choose();
                head.IsChecked = _values.Get(cards) == key;
            };
            var inside = new StackPanel();
            bool chosen = _values.Get(cards) == key;
            Control Part(Field field)
            {
                var caption = new TextBlock { Classes = { "caption" }, Text = field.Name, Margin = new Thickness(1, 2, 0, 3) };
                if (field.Tip.Length > 0) ToolTip.SetTip(caption, field.Tip);
                // The chosen card shows the choices as the server holds them - an encoder this machine did not pass is off;
                // a card not chosen shows those of the manifest.
                return new StackPanel { Children = { caption, Choice(field, asHeld: chosen, before: Choose) } };
            }
            // A choice of a few - three and fewer - stands beside the next such choice: Quality at the left, Container at the
            // right (the owner, 18.10.2026: "Разве нельзя поставить качество слева, контейнер справа и сэкономить высоту?");
            // a longer one - the encoder - takes the width of the card.
            var shown = node.Fields.Where(field => field.ShownFor(cards.Id).Contains(key)).ToList();
            static bool Short(Field field) => field.Options.Count is > 0 and <= 3;
            for (int at = 0; at < shown.Count; at++)
            {
                if (Short(shown[at]) && at + 1 < shown.Count && Short(shown[at + 1]))
                {
                    inside.Children.Add(new PairRow { Children = { Part(shown[at]), Part(shown[at + 1]) } });
                    at++;
                    continue;
                }
                inside.Children.Add(Part(shown[at]));
            }
            var column = new StackPanel { Children = { head, inside } };
            var card = new Border { Classes = { "codeccard" }, Child = column };
            // The glow of the chosen card is a plate of its own under it, with nothing inside: a shadow on a border that
            // holds controls was drawn with its controls moved away from it.
            var halo = new Border { Classes = { "codecglow" }, IsHitTestVisible = false, IsVisible = false };
            var place = new Panel { Children = { halo, card } };
            Grid.SetColumn(place, grid.ColumnDefinitions.Count - 1);
            grid.Children.Add(place);
            faces.Add((card, halo, head, inside, key));
        }
        Watch(cards, () =>
        {
            var current = _values.Get(cards);
            foreach (var (card, halo, head, body, key) in faces)
            {
                bool on = key == current;
                head.IsChecked = on;
                card.Classes.Set("on", on);
                halo.IsVisible = on;
                halo.BoxShadow = on ? Glow() : default;
                // The cards not chosen are shaded, their words kept readable: what they hold stays at hand.
                body.Opacity = on ? 1 : 0.55;
            }
        });
        return grid;
    }

    /// <summary>
    /// The neon glow round the rim of a chosen card: the accent of the theme, soft and wide, under its sharp rim. Made from
    /// the theme in sight - a theme changed builds the form again.
    /// </summary>
    static BoxShadows Glow()
    {
        var accent = Application.Current is { } app && app.TryFindResource("Quasar", app.ActualThemeVariant, out var found) && found is ISolidColorBrush brush
            ? brush.Color : Color.Parse("#2e8fc4");
        return new BoxShadows(
            new BoxShadow { Blur = 14, Spread = 1, Color = Color.FromArgb(150, accent.R, accent.G, accent.B) },
            new[] { new BoxShadow { Blur = 4, Spread = 0, Color = Color.FromArgb(200, accent.R, accent.G, accent.B) } });
    }

    TextBox TextBox(Field field)
    {
        var box = new TextBox { PlaceholderText = field.Placeholder, Classes = { "masks" }, MinHeight = 24, Padding = new Thickness(8, 2), VerticalContentAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, 4) };
        PixelGrid.Field(box);
        Avalonia.Automation.AutomationProperties.SetAutomationId(box, "field_" + field.Id);
        if (field.Tip.Length > 0) ToolTip.SetTip(box, field.Tip);
        // A text goes to the server when it is taken - Enter, or the box let go - not at every letter.
        void Take() { if ((box.Text ?? "") != _values.Get(field)) _values.Set(field, box.Text ?? ""); }
        box.LostFocus += (_, _) => Take();
        box.KeyDown += (_, e) => { if (e.Key == Key.Enter) { Take(); e.Handled = true; } };
        // The box a person types in is not rewritten under the cursor: only a value that came from elsewhere is put in.
        Watch(field, () => { if (!box.IsFocused && (box.Text ?? "") != _values.Get(field)) box.Text = _values.Get(field); });
        return box;
    }

    /// <summary>The body of a block with the stripe of its block at its left: the mark the blocks of the former window had.</summary>
    static Control Striped(Control body, string block)
    {
        var stripe = new Border { Classes = { "stripe", "g-" + (block.Length > 0 ? block : "parameters") } };
        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*") };
        grid.Children.Add(stripe);
        Grid.SetColumn(body, 1);
        grid.Children.Add(body);
        return grid;
    }

    /// <summary>
    /// A number: the slider in a dark chip and the box of the number beside it, as Audion Image Tools has them (the owner,
    /// 18.10.2026: "сделаем ползунки компактными ... с красивыми тёмными чипами под ползунками"). The box is typed - Enter
    /// or leaving it takes the number - or stepped with the arrow keys; the slider moves it by its step. Kept inside min and
    /// max of the manifest; a slider let go after a pause of a fifth of a second is told to the server once, not at every
    /// pixel.
    /// </summary>
    Control NumberBox(Field field)
    {
        double step = field.Step is { } given && given > 0 ? given : 1;
        double min = field.Min ?? 0, max = field.Max ?? Math.Max(min + step * 100, 1);
        string Show(double number) => number.ToString(step >= 1 ? "0" : step >= 0.1 ? "0.0#" : "0.0##", CultureInfo.InvariantCulture);
        double Fit(double number) => Math.Clamp(Math.Round(Math.Round((number - min) / step) * step + min, 6), min, max);

        var box = new TextBox
        {
            Width = 64, Classes = { "masks", "chipnum" }, Height = 24, MinHeight = 24, Padding = new Thickness(6, 0), VerticalContentAlignment = VerticalAlignment.Center,
            HorizontalContentAlignment = HorizontalAlignment.Right,
        };
        Avalonia.Automation.AutomationProperties.SetAutomationId(box, "field_" + field.Id);
        PixelGrid.Field(box);
        var slider = new Slider { Minimum = min, Maximum = max, SmallChange = step, LargeChange = step * 10, TickFrequency = step, IsSnapToTickEnabled = true, MinWidth = 110 };
        Avalonia.Automation.AutomationProperties.SetAutomationId(slider, "slide_" + field.Id);
        IBrush? accent = Application.Current is { } app && app.TryFindResource("Quasar", app.ActualThemeVariant, out var found) ? found as IBrush : null;
        var chip = Chip(slider, accent);
        chip.Margin = new Thickness(0, 0, 8, 0);
        Grid.SetColumn(box, 1);
        var line = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), MinWidth = 200, Margin = new Thickness(0, 0, 0, 4), Children = { chip, box } };
        if (field.Tip.Length > 0)
        {
            var tip = field.Tip + "\n\n" + Lang.F("От {0} до {1}, шаг {2}.", Show(min), Show(max), Show(step));
            ToolTip.SetTip(chip, tip);
            ToolTip.SetTip(box, tip);
        }

        bool painting = false;
        var settle = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };
        settle.Tick += (_, _) =>
        {
            settle.Stop();
            _values.Set(field, Show(Fit(slider.Value)));
        };
        void Take()
        {
            var typed = (box.Text ?? "").Trim().Replace(',', '.');
            if (double.TryParse(typed, NumberStyles.Float, CultureInfo.InvariantCulture, out var number)) _values.Set(field, Show(Fit(number)));
            Paint();
        }
        void Move(int direction)
        {
            if (!double.TryParse(_values.Get(field), NumberStyles.Float, CultureInfo.InvariantCulture, out var number)) number = min;
            _values.Set(field, Show(Fit(number + direction * step)));
            Paint();
        }
        void Paint()
        {
            painting = true;
            if (double.TryParse(_values.Get(field), NumberStyles.Float, CultureInfo.InvariantCulture, out var number))
            {
                if (!box.IsFocused) box.Text = Show(number);
                slider.Value = number;
            }
            painting = false;
        }
        slider.PropertyChanged += (_, e) =>
        {
            if (e.Property != RangeBase.ValueProperty || painting) return;
            box.Text = Show(Fit(slider.Value));
            settle.Stop();
            settle.Start();
        };
        box.LostFocus += (_, _) => Take();
        box.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter) { Take(); e.Handled = true; }
            else if (e.Key == Key.Up) { Take(); Move(1); e.Handled = true; }
            else if (e.Key == Key.Down) { Take(); Move(-1); e.Handled = true; }
        };
        Watch(field, Paint);
        return line;
    }

    /// <summary>
    /// A slider as the owner asked for it in Audion Image Tools (14.10.2026: "smaller circles, and prettier - each in a dark
    /// chip with rounded corners"): a thumb of 12, a thin track, the slider in a chip as dark and as tall as a field beside
    /// it. The filled part and the thumb wear <paramref name="tone"/>, the accent of the theme.
    /// </summary>
    static Border Chip(Slider slider, IBrush? tone)
    {
        // The air the theme leaves over and under a slider (15 and 15) would push it out of a chip as tall as a field.
        slider.Resources["SliderPreContentMargin"] = new GridLength(0);
        slider.Resources["SliderPostContentMargin"] = new GridLength(0);
        slider.Resources["SliderOutsideTickBarThemeHeight"] = 0.0;
        slider.Resources["SliderHorizontalHeight"] = 22.0;
        slider.Resources["SliderHorizontalThumbWidth"] = 12.0;
        slider.Resources["SliderHorizontalThumbHeight"] = 12.0;
        slider.Resources["SliderThumbCornerRadius"] = new CornerRadius(6);
        slider.Resources["SliderTrackThemeHeight"] = 3.0;
        if (tone is not null)
        {
            foreach (var key in new[] { "SliderTrackValueFill", "SliderTrackValueFillPointerOver", "SliderTrackValueFillPressed" })
                slider.Resources[key] = tone;
            foreach (var key in new[] { "SliderThumbBackground", "SliderThumbBackgroundPointerOver", "SliderThumbBackgroundPressed" })
                slider.Resources[key] = tone;
        }
        slider.Height = 22;
        slider.VerticalAlignment = VerticalAlignment.Center;
        slider.Margin = new Thickness(0);
        // A dark ring around the thumb (App.axaml, Slider.chip).
        slider.Classes.Add("chip");
        var chip = new Border
        {
            CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1), Padding = new Thickness(8, 0),
            Height = 24, VerticalAlignment = VerticalAlignment.Center, Child = slider, ClipToBounds = true,
        };
        chip.Bind(Border.BackgroundProperty, chip.GetResourceObservable("ChipBg"));
        chip.Bind(Border.BorderBrushProperty, chip.GetResourceObservable("BorderSoft"));
        // The thumb in the middle of the strip: where the template of the theme puts it is measured once it is laid out,
        // and the slider is moved by what is left - no number guessed by eye.
        void Centre(object? sender, EventArgs e)
        {
            if (slider.GetVisualDescendants().OfType<Thumb>().FirstOrDefault() is not { } thumb || thumb.Bounds.Height <= 0 || chip.Bounds.Height <= 0) return;
            if (thumb.TranslatePoint(new Point(0, thumb.Bounds.Height / 2), chip) is not { } middle) return;
            double off = (chip.Bounds.Height - chip.BorderThickness.Top - chip.BorderThickness.Bottom) / 2 + chip.BorderThickness.Top - middle.Y;
            if (Math.Abs(off) < 0.5) { slider.LayoutUpdated -= Centre; return; }
            slider.Margin = new Thickness(0, slider.Margin.Top + off, 0, slider.Margin.Bottom - off);
        }
        slider.LayoutUpdated += Centre;
        return chip;
    }
}
