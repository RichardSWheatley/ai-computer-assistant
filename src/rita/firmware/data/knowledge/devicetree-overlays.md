# Devicetree overlays

Source: https://docs.zephyrproject.org/latest/build/dts/howtos.html
(researched 2026-07-28)

Overlays modify the board's devicetree without touching board files. The
build system auto-discovers, in order (first hit wins):
`socs/<SOC>_<QUALIFIERS>.overlay`, `boards/<BOARD>.overlay`,
`<BOARD>.overlay`, `app.overlay`. Extra files:
`-DEXTRA_DTC_OVERLAY_FILE="a.overlay;b.overlay"` (highest precedence).

Common patterns:

```dts
&uart0 { status = "okay"; current-speed = <115200>; };

&spi1 {
    sensor0: sensor@0 {
        compatible = "vendor,part";
        reg = <0>;
        spi-max-frequency = <DT_FREQ_M(4)>;
    };
};

/ {
    aliases { led0 = &led_0; };
    chosen { zephyr,console = &uart0; };
};
```

Debug what actually got built: `build/zephyr/zephyr.dts` (final merged
tree) and `devicetree_generated.h`.
