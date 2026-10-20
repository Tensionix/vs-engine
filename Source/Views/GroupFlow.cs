using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;

namespace AudionVSEngine.Views;

/// <summary>
/// The groups of the presets of a palette by the kind of processing (the owner, 18.10.2026: "распределим все группы
/// пресетов по переключателям для каждого вида обработки"): each group a caption and its switches. The groups stand side
/// by side while their natural widths fit the line, the next goes under them; the groups of a line share its width by
/// their natural widths, so no lone switch is stretched over the window and none of them is cut. A thin rule
/// (<see cref="Rule"/>, put between two groups by whoever fills the panel) stands in the gap between two groups of one
/// line and is not shown between the last group of a line and the first of the next.
/// </summary>
public sealed class GroupFlow : Panel
{
    /// <summary>The gap between two groups of a line; the rule stands in its middle.</summary>
    public double Gap { get; set; } = 21;
    /// <summary>The gap between two lines of groups.</summary>
    public double LineGap { get; set; } = 6;

    /// <summary>A rule between two groups: a child of the panel as the groups are, laid in the gap.</summary>
    public static Border Rule()
    {
        var rule = new Border { Width = 1, Tag = RuleTag, IsHitTestVisible = false };
        rule.Bind(Border.BackgroundProperty, rule.GetResourceObservable("SepInk"));
        return rule;
    }

    const string RuleTag = "group-rule";
    static bool IsRule(Control child) => child.Tag as string == RuleTag;

    List<List<Control>> _lines = new();

    IEnumerable<Control> Groups => Children.Where(child => child.IsVisible && !IsRule(child));

    protected override Size MeasureOverride(Size availableSize)
    {
        var shown = Groups.ToList();
        foreach (var child in Children.Where(IsRule)) child.Measure(new Size(1, 1));
        foreach (var child in shown) child.Measure(new Size(double.PositiveInfinity, availableSize.Height));
        double width = availableSize.Width;
        _lines = new List<List<Control>>();
        var line = new List<Control>();
        foreach (var child in shown)
        {
            if (line.Count > 0 && !double.IsInfinity(width) && Natural(line) + Gap + child.DesiredSize.Width > width)
            {
                _lines.Add(line);
                line = new List<Control>();
            }
            line.Add(child);
        }
        if (line.Count > 0) _lines.Add(line);
        if (double.IsInfinity(width)) return new Size(_lines.Select(Natural).DefaultIfEmpty(0).Max(), _lines.Sum(Tall) + LineGap * Math.Max(0, _lines.Count - 1));
        // Measured again at the width each will have: a group stretched may lay its switches on one line where it wrapped.
        double height = 0;
        foreach (var one in _lines)
        {
            var widths = Shares(one, width);
            for (int i = 0; i < one.Count; i++) one[i].Measure(new Size(widths[i], availableSize.Height));
            height += Tall(one);
        }
        return new Size(width, height + LineGap * Math.Max(0, _lines.Count - 1));
    }

    double Natural(List<Control> line) => line.Sum(child => child.DesiredSize.Width) + Gap * Math.Max(0, line.Count - 1);

    static double Tall(List<Control> line) => line.Select(child => child.DesiredSize.Height).DefaultIfEmpty(0).Max();

    /// <summary>The widths of the groups of a line: their natural widths, the room left shared in their proportion.</summary>
    double[] Shares(List<Control> line, double width)
    {
        double natural = line.Sum(child => child.DesiredSize.Width);
        double room = Math.Max(0, width - Gap * (line.Count - 1));
        return line.Select(child => natural > 0 ? room * child.DesiredSize.Width / natural : room / line.Count).ToArray();
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        // Where each group stands, to put the rule that follows it.
        var placed = new Dictionary<Control, (Rect Box, int Line)>();
        double top = 0;
        for (int at = 0; at < _lines.Count; at++)
        {
            var line = _lines[at];
            double tall = Tall(line), left = 0;
            var widths = Shares(line, finalSize.Width);
            for (int i = 0; i < line.Count; i++)
            {
                var box = new Rect(left, top, widths[i], tall);
                line[i].Arrange(box);
                placed[line[i]] = (box, at);
                left += widths[i] + Gap;
            }
            top += tall + LineGap;
        }
        // A rule between two groups of one line stands in the middle of their gap; between two lines it is not shown.
        var children = Children.ToList();
        for (int i = 0; i < children.Count; i++)
        {
            if (!IsRule(children[i])) continue;
            var before = children.Take(i).LastOrDefault(child => !IsRule(child) && placed.ContainsKey(child));
            var after = children.Skip(i + 1).FirstOrDefault(child => !IsRule(child) && placed.ContainsKey(child));
            if (before is not null && after is not null && placed[before].Line == placed[after].Line)
            {
                var (box, _) = placed[before];
                children[i].Arrange(new Rect(Math.Round(box.Right + Gap / 2), box.Top + 3, 1, Math.Max(0, box.Height - 6)));
            }
            else children[i].Arrange(new Rect(0, 0, 0, 0));
        }
        return finalSize;
    }
}
