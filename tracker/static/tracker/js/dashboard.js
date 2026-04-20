(function () {
    const chartData = window.dashboardChartData;
    if (!chartData || typeof Chart === "undefined") {
        return;
    }

    const baseColors = [
        "#FF6384",
        "#36A2EB",
        "#FFCE56",
        "#4BC0C0",
        "#9966FF",
        "#FF9F40",
    ];

    function getCategoryColors(labels) {
        return labels.map((_, index) => baseColors[index % baseColors.length]);
    }

    const totalCenterPlugin = {
        id: "totalCenterPlugin",
        afterDraw(chart) {
            if (chart.config.type !== "doughnut") return;
            const dataset = chart.config.data.datasets[0];
            if (!dataset || !dataset.data || !dataset.data.length) return;

            const total = dataset.data.reduce((sum, value) => sum + Number(value || 0), 0);
            const { ctx, chartArea } = chart;
            const centerX = (chartArea.left + chartArea.right) / 2;
            const centerY = (chartArea.top + chartArea.bottom) / 2;

            ctx.save();
            ctx.textAlign = "center";
            ctx.fillStyle = "#475569";
            ctx.font = "600 12px Segoe UI";
            ctx.fillText("Total Spend", centerX, centerY - 8);
            ctx.fillStyle = "#111827";
            ctx.font = "700 16px Segoe UI";
            ctx.fillText("Rs " + total.toFixed(2), centerX, centerY + 14);
            ctx.restore();
        },
    };

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
    };

    const pieCanvas = document.getElementById("categoryPieChart");
    if (pieCanvas && chartData.values.length) {
        new Chart(pieCanvas, {
            type: "doughnut",
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        data: chartData.values,
                        backgroundColor: getCategoryColors(chartData.labels),
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                ...commonOptions,
                plugins: {
                    legend: { position: "bottom" },
                },
            },
            plugins: [totalCenterPlugin],
        });
    }

    const barCanvas = document.getElementById("monthlyBarChart");
    if (barCanvas && chartData.monthValues.length) {
        new Chart(barCanvas, {
            type: "bar",
            data: {
                labels: chartData.monthLabels,
                datasets: [
                    {
                        label: "Monthly Spend",
                        data: chartData.monthValues,
                        backgroundColor: "#4f46e5",
                        borderRadius: 8,
                    },
                ],
            },
            options: {
                ...commonOptions,
                scales: {
                    y: { beginAtZero: true },
                },
            },
        });
    }

    const lineCanvas = document.getElementById("trendLineChart");
    if (lineCanvas && chartData.trendValues.length) {
        new Chart(lineCanvas, {
            type: "line",
            data: {
                labels: chartData.trendLabels,
                datasets: [
                    {
                        label: "Expense Trend",
                        data: chartData.trendValues,
                        fill: false,
                        borderColor: "#0ea5e9",
                        tension: 0.35,
                        pointBackgroundColor: "#0ea5e9",
                    },
                ],
            },
            options: {
                ...commonOptions,
                scales: {
                    y: { beginAtZero: true },
                },
            },
        });
    }
})();
