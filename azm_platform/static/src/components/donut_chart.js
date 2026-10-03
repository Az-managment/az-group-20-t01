import { Component, t, useProps } from "@odoo/owl";

/**
 * Lightweight SVG donut chart (no external library).
 * data: [{ name, color, count }]
 */
export class AzmDonutChart extends Component {
    static template = "azm_platform.DonutChart";
    props = useProps({
        data: t.array(),
        size: t.number().optional(),
        thickness: t.number().optional(),
        centerValue: t.any().optional(),
        centerLabel: t.string().optional(),
        emptyLabel: t.string().optional(),
    });

    get size() {
        return this.props.size || 200;
    }
    get thickness() {
        return this.props.thickness || 30;
    }
    get radius() {
        return (this.size - this.thickness) / 2;
    }
    get circumference() {
        return 2 * Math.PI * this.radius;
    }
    get centerText() {
        if (!this.total) {
            return "—";
        }
        return this.props.centerValue !== undefined ? this.props.centerValue : this.total;
    }
    get subText() {
        return this.total ? this.props.centerLabel || "" : this.props.emptyLabel || this.props.centerLabel || "";
    }
    get total() {
        return this.props.data.reduce((sum, d) => sum + (d.count || 0), 0);
    }
    /** When there is no data, show equal "ghost" slices so the design stays readable. */
    get segments() {
        const data = this.props.data;
        const total = this.total;
        const gap = data.length > 1 ? 2 : 0;
        let offset = 0;
        return data.map((d) => {
            const share = total ? (d.count || 0) / total : 1 / Math.max(data.length, 1);
            const length = Math.max(share * this.circumference - gap, 0);
            const segment = {
                key: d.id ?? d.name,
                color: d.color,
                dash: `${length} ${this.circumference - length}`,
                offset: -offset,
                title: `${d.name}: ${d.count || 0}`,
                muted: !total,
            };
            offset += share * this.circumference;
            return segment;
        });
    }
}
