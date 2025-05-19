"""
UniversalPlotterPlotly.py

Live CSV plotter using Dash and Plotly.
Provides real-time visualization of CSV data with predefined and custom scatter plots,
status cards for selected fields, and automatic refresh at specified intervals.
"""

import socket
import pandas as pd
from dash import Dash, dcc, html, Input, Output, State
import plotly.express as px

# Constants defining the expected CSV header fields
HEADER = (
        "T_A[K] T_B[K] Setpoint[K] "
        "SR860x[V] SR860y[V] SR860f[Hz] "
        "SR860sin[V] SR860theta[deg] "
        "SR860phase[deg] SR860mag[V] "
        "HTR dTdt CNT DateTime"
)
FIELD_NAMES = HEADER.split()  # List of field names parsed from HEADER

def get_local_ip():
    """
    Determine the local IP address for network access.
    Tries connecting to a public DNS server and retrieves the socket's own IP.
    Falls back to localhost if any exception occurs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Use Google's public DNS server address
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class LivePlotlyApp:
    """
    Dash application for live plotting CSV data.
    Supports predefined plots, dynamic custom plots, and status cards.
    """
    def __init__(self, file_path, predefined_plots, cols, sep, refresh_ms):
        """
        Initialize the live plotter application.

        :param file_path: Path to the CSV data file.
        :param predefined_plots: List of strings 'x,y' defining default scatter plots.
        :param cols: Number of columns in the predefined plots layout.
        :param sep: CSV separator character.
        :param refresh_ms: Refresh interval in milliseconds.
        """
        self.file_path = file_path
        # Split each 'x,y' string into [x, y] lists
        self.predefined_plots = [p.split(',') for p in predefined_plots]
        self.cols = cols
        self.sep = sep
        self.refresh_ms = refresh_ms

    def run(self, host, port, debug):
        """
        Configure and run the Dash server.

        :param host: Interface to bind the server.
        :param port: Port number for the server.
        :param debug: Enable Dash debug mode if True.
        """
        app = Dash(__name__)

        # Store component for persisting custom plot definitions
        store = dcc.Store(id='custom-plots', data=[])

        # Control panel for adding custom scatter plots at runtime
        controls = html.Div([
            dcc.Dropdown(
                id='x-axis-dropdown',
                options=[{'label': f, 'value': f} for f in FIELD_NAMES],
                placeholder='Select X axis'
            ),
            dcc.Dropdown(
                id='y-axis-dropdown',
                options=[{'label': f, 'value': f} for f in FIELD_NAMES],
                placeholder='Select Y axis',
                style={'marginTop': '8px'}
            ),
            html.Button(
                'Add Graph',
                id='add-graph-button',
                n_clicks=0,
                style={
                    'padding': '10px 20px',
                    'backgroundColor': '#007bff',
                    'color': '#fff',
                    'border': 'none',
                    'borderRadius': '4px',
                    'cursor': 'pointer',
                    'fontSize': '14px',
                    'marginTop': '12px'
                }
            )
        ], style={'display': 'inline-block', 'verticalAlign': 'top', 'width': '25%', 'fontFamily': 'Arial'})

        # Selector for which status cards to display
        card_selector = html.Div([
            html.Label('Status cards:', style={'fontWeight': 'bold'}),
            dcc.Checklist(
                id='card-selector',
                options=[{'label': f, 'value': f} for f in FIELD_NAMES],
                value=['T_A[K]', 'T_B[K]', 'SR860x[V]', 'SR860y[V]','dTdt','Setpoint[K]'],
                labelStyle={
                    'display': 'inline-block',
                    'margin': '5px 10px',
                    'padding': '5px',
                    'border': '1px solid #ccc',
                    'borderRadius': '3px',
                    'cursor': 'pointer'
                },
                inputStyle={'marginRight': '5px'}
            )
        ], style={'marginTop': '20px', 'marginBottom': '20px', 'fontFamily': 'Arial'})

        # Containers layout for custom graphs, status cards, and predefined plots
        custom_container = html.Div(
            id='custom-graphs-container',
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(2, 1fr)', 'gap': '20px'}
        )
        status_container = html.Div(
            id='status-box',
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(3, 1fr)', 'gap': '15px', 'marginBottom': '20px'}
        )
        predefined_graphs = html.Div(
            [dcc.Graph(id=f'plot-{i}', config={'scrollZoom': True}) for i in range(len(self.predefined_plots))],
            style={'display': 'grid', 'gridTemplateColumns': f'repeat({self.cols}, 1fr)', 'gap': '20px'}
        )

        # Assemble the full application layout
        app.layout = html.Div([
            store,
            controls,
            custom_container,
            card_selector,
            status_container,
            predefined_graphs,
            dcc.Interval(id='interval-component', interval=self.refresh_ms, n_intervals=0)
        ], style={'width': '90%', 'margin': 'auto', 'fontFamily': 'Arial'})

        @app.callback(
            Output('custom-plots', 'data'),
            Input('add-graph-button', 'n_clicks'),
            State('x-axis-dropdown', 'value'),
            State('y-axis-dropdown', 'value'),
            State('custom-plots', 'data')
        )
        def add_plot(n_clicks, x_axis, y_axis, data):
            """
            Callback to add a new custom plot definition when the button is clicked.
            """
            if n_clicks and x_axis and y_axis:
                data.append({'x': x_axis, 'y': y_axis})
            return data

        # Prepare outputs for predefined figures, status cards, and custom graphs
        outputs = [Output(f'plot-{i}', 'figure') for i in range(len(self.predefined_plots))]
        outputs.extend([Output('status-box', 'children'), Output('custom-graphs-container', 'children')])

        @app.callback(
            outputs,
            [Input('interval-component', 'n_intervals'),
             Input('custom-plots', 'data'),
             Input('card-selector', 'value')]
        )
        def update_all(n_intervals, custom_data, selected_cards):
            """
            Main update callback that refreshes all figures and status cards.

            :param n_intervals: Interval update counter
            :param custom_data: List of custom plot definitions
            :param selected_cards: Fields selected for status display
            """
            # Read the latest data from CSV
            df = pd.read_csv(self.file_path, sep=self.sep)

            # Generate figures for each predefined plot
            figs = []
            for x_col, y_col in self.predefined_plots:
                fig = px.line(df, x=x_col, y=y_col, title=f"{y_col} vs {x_col}", labels={x_col: x_col, y_col: y_col},markers=True)
                fig.update_layout(uirevision='keep_zoom')
                figs.append(fig)

            # Build status cards based on the most recent row
            last_row = df.iloc[-1]
            cards = []
            for field in selected_cards:
                cards.append(html.Div([
                    html.Div(field, style={'fontWeight': 'bold'}),
                    html.Div(str(last_row[field]), style={'fontSize': '16px', 'marginTop': '5px'})
                ], style={'border': '1px solid #ccc', 'borderRadius': '4px', 'padding': '10px', 'backgroundColor': '#fff'}))

            # Create custom scatter plots defined by the user
            custom_children = []
            for pair in custom_data or []:
                fig = px.scatter(df, x=pair['x'], y=pair['y'], title=f"{pair['y']} vs {pair['x']}", labels={pair['x']: pair['x'], pair['y']: pair['y']})
                fig.update_layout(uirevision='keep_zoom')
                custom_children.append(html.Div(dcc.Graph(figure=fig, config={'scrollZoom': True}), style={'borderRadius': '4px'}))

            # Return all updated components: predefined figures, status cards, and custom graphs
            return [*figs, cards, custom_children]

        # Display server URLs to console
        display_ip = get_local_ip() if host == '0.0.0.0' else host
        print("Dash app is running!")
        print(f"• Local:   http://127.0.0.1:{port}")
        print(f"• Network: http://{display_ip}:{port}")

        # Launch the Dash server
        app.run(host=host, port=port, debug=True, dev_tools_silence_routes_logging=True)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Live CSV plotter using Dash and Plotly"
    )
    parser.add_argument("-f", "--file", required=True, help="Path to data CSV")
    parser.add_argument("-p", "--plot", nargs="+", required=True, help="Predefined plots as X,Y pairs")
    parser.add_argument("-c", "--cols", type=int, default=2, help="Number of columns in layout")
    parser.add_argument("-s", "--sep", default=",", help="CSV separator")
    parser.add_argument("-i", "--interval", type=int, default=1000, help="Refresh interval in milliseconds")
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=8050, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable Dash debug mode")
    args = parser.parse_args()

    # Instantiate and run the Dash app with provided arguments
    app = LivePlotlyApp(
        file_path=args.file,
        predefined_plots=args.plot,
        cols=args.cols,
        sep=args.sep,
        refresh_ms=args.interval
    )
    app.run(host=args.host, port=args.port, debug=args.debug)