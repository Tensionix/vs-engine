using System;
using System.Linq;
using Avalonia;
using Avalonia.Controls;

namespace AudionVSEngine.Views;

/// <summary>
/// Two choices on one line - the first as wide as its switches, the second the rest - while both fit without wrapping a
/// switch; one under the other when they do not (the owner, 18.10.2026, of the cards of the encoder: "Разве нельзя
/// поставить качество слева, контейнер справа и сэкономить высоту?"). The natural widths are measured in the pass of the
/// panel itself, when the switches already wear their style. Between the two on one line there is always a rule, short
/// and quiet (the owner, 18.10.2026: "Делаем разделитель между колонками всегда, хотя бы короткий и неконтрастный").
/// </summary>
public sealed class PairRow : Panel
{
    public double Gap { get; set; } = 15;
    public double LineGap { get; set; } = 0;
    /// <summary>How much of the height of the line the rule takes, in its middle.</summary>
    public double RuleShare { get; set; } = 0.7;

    bool _beside = true;
    readonly Border _rule;

    public PairRow()
    {
        _rule = new Border { Width = 1, IsHitTestVisible = false, Opacity = 0.7 };
        _rule.Bind(Border.BackgroundProperty, _rule.GetResourceObservable("SepInk"));
        Children.Add(_rule);
    }

    System.Collections.Generic.List<Control> Parts() => Children.Where(child => child != _rule && child.IsVisible).Take(2).ToList();

    protected override Size MeasureOverride(Size availableSize)
    {
        _rule.Measure(new Size(1, 1));
        var parts = Parts();
        if (parts.Count < 2)
        {
            foreach (var child in parts) child.Measure(availableSize);
            return parts.Count == 0 ? default : parts[0].DesiredSize;
        }
        foreach (var child in parts) child.Measure(new Size(double.PositiveInfinity, availableSize.Height));
        double natural = parts[0].DesiredSize.Width + Gap + parts[1].DesiredSize.Width;
        _beside = double.IsInfinity(availableSize.Width) || natural <= availableSize.Width + 0.5;
        if (_beside)
        {
            double rest = double.IsInfinity(availableSize.Width) ? parts[1].DesiredSize.Width : availableSize.Width - parts[0].DesiredSize.Width - Gap;
            parts[1].Measure(new Size(Math.Max(0, rest), availableSize.Height));
            return new Size(double.IsInfinity(availableSize.Width) ? natural : availableSize.Width,
                            Math.Max(parts[0].DesiredSize.Height, parts[1].DesiredSize.Height));
        }
        foreach (var child in parts) child.Measure(new Size(availableSize.Width, availableSize.Height));
        return new Size(availableSize.Width, parts[0].DesiredSize.Height + LineGap + parts[1].DesiredSize.Height);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        var parts = Parts();
        _rule.Arrange(new Rect(0, 0, 0, 0));
        if (parts.Count < 2)
        {
            foreach (var child in parts) child.Arrange(new Rect(finalSize));
            return finalSize;
        }
        if (_beside)
        {
            double first = parts[0].DesiredSize.Width;
            parts[0].Arrange(new Rect(0, 0, first, finalSize.Height));
            parts[1].Arrange(new Rect(first + Gap, 0, Math.Max(0, finalSize.Width - first - Gap), finalSize.Height));
            double tall = finalSize.Height * RuleShare;
            _rule.Arrange(new Rect(Math.Round(first + Gap / 2), (finalSize.Height - tall) / 2, 1, tall));
        }
        else
        {
            double top = parts[0].DesiredSize.Height;
            parts[0].Arrange(new Rect(0, 0, finalSize.Width, top));
            parts[1].Arrange(new Rect(0, top + LineGap, finalSize.Width, parts[1].DesiredSize.Height));
        }
        return finalSize;
    }
}
