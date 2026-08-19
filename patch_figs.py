import re
src = open("make_figures.py", encoding="utf-8").read()

# fig2: include the 10-min points in the y-limits, move legend clear
src = src.replace(
'''    ax.axvspan(-3.2, -1.6, color=GREY, alpha=0.10)''',
'''    lo_all = min(min(l.get_ydata()) for l in ax.get_lines() if len(l.get_ydata()))
    hi_all = max(max(l.get_ydata()) for l in ax.get_lines() if len(l.get_ydata()))
    pad = (hi_all - lo_all) * 0.18
    ax.set_ylim(lo_all - pad, hi_all + pad)
    ax.axvspan(-3.2, -1.6, color=GREY, alpha=0.10)''')
src = src.replace(
'''    ax.legend(fontsize=8, title="patch", title_fontsize=8, loc="lower left")''',
'''    ax.legend(fontsize=8, title="patch", title_fontsize=8,
              loc="upper center", bbox_to_anchor=(0.5, -0.04), ncol=2,
              frameon=False)''')

# fig3: real log ticks, legend outside
src = src.replace(
'''    ax.set_yscale("log")''',
'''    ax.set_yscale("log")
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0])
    ax.set_yticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2", "3"])
    ax.minorticks_off()''')
src = src.replace(
'''    ax.legend(fontsize=8, loc="center right")''',
'''    ax.legend(fontsize=8, loc="upper left", frameon=False)''')

# fig4: legend outside the axes
src = src.replace(
'''    ax.legend(fontsize=8, loc="lower left")''',
'''    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=2, frameon=False)''')

open("make_figures.py", "w", encoding="utf-8").write(src)
print("patched")
