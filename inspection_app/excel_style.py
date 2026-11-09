"""Shared engineering-report palette and chart defaults for Excel outputs."""

NAVY='173F46'
BLUE='E4F0F1'
RED='FBE7E2'


def configure_month_chart(chart,category_reference):
    """Use text month labels and explicit axes; Excel otherwise hides tick labels."""
    chart.x_axis.tickLblPos='nextTo'
    chart.y_axis.tickLblPos='nextTo'
    chart.x_axis.delete=False
    chart.y_axis.delete=False
    chart.y_axis.numFmt='0'
    chart.y_axis.scaling.min=0
    chart.y_axis.majorUnit=1
