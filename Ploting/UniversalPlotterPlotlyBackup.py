import difflib
import io
import socket
import uuid
import pandas as pd
import plotly.express as px
import requests


from itertools import cycle
from dash import Dash, dcc, html, Input, Output, State
from flask import send_file, request, url_for

# Constants defining the expected CSV header fields
HEADER = (
        "T_A[K] T_B[K] Setpoint[K] "
        "SR860x[V] SR860y[V] SR860f[Hz] "
        "SR860sin[V] SR860theta[deg] "
        "SR860phase[deg] SR860mag[V] "
        "HTR dTdt[K/min] CNT DateTime"
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
        self.ULTRAMSG_INSTANCE_ID = "instance121596"
        self.ULTRAMSG_TOKEN = "0b81z4fm8m3w6a4s"

    def run(self, host, port, debug):
        """
        Configure and run the Dash server.

        :param host: Interface to bind the server.
        :param port: Port number for the server.
        :param debug: Enable Dash debug mode if True.
        """
        app = Dash(__name__)
        server = app.server

        app.server.config['BASIC_AUTH_REALM'] = f"PlotterRealm-{uuid.uuid4()}"
        secret_key = uuid.uuid4().hex
        app.server.secret_key = secret_key

        # Define valid username/password pairs
        VALID_USERNAME_PASSWORD_PAIRS = {
            'user': '6969666',
        }

        # Apply Basic Auth to the Dash app
        #dash_auth.BasicAuth(app, VALID_USERNAME_PASSWORD_PAIRS)

        # Store component for persisting custom plot definitions
        store = dcc.Store(id='custom-plots', data=[])


        # Selector for which status cards to display
        card_selector = html.Div([
            html.Label('Status cards:', style={'fontWeight': 'bold'}),
            dcc.Checklist(
                id='card-selector',
                options=[{'label': f, 'value': f} for f in FIELD_NAMES],
                value=['T_A[K]', 'T_B[K]', 'SR860x[V]', 'SR860y[V]','dTdt[K/min]','Setpoint[K]'],
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


        status_container = html.Div(
            id='status-box',
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(3, 1fr)', 'gap': '15px', 'marginBottom': '20px'}
        )
        predefined_graphs = html.Div(
            [dcc.Graph(id=f'plot-{i}', config={'scrollZoom': True}) for i in range(len(self.predefined_plots))],
            style={'display': 'grid', 'gridTemplateColumns': f'repeat({self.cols}, 1fr)', 'gap': '20px'}
        )

        # Containers layout for custom graphs, status cards, and predefined plots
        custom_container = html.Div(
            id='custom-graphs-container',
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(2, 1fr)', 'gap': '20px'}
        )

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


        @server.route('/snapshot/<int:idx>.png')
        def snapshot(idx):
            # 1) Read fresh data
            df = pd.read_csv(self.file_path, sep=self.sep)

            # 2) Style setup
            palette = px.colors.qualitative.Vivid
            template = 'ggplot2'
            color = palette[idx % len(palette)]

            # 3) Pick the (x, y) pair for this predefined plot
            x_col, y_col = self.predefined_plots[idx]

            # 4) Rebuild exactly the same figure you use in update_all()
            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                title=f"{y_col} vs {x_col}",
                labels={x_col: x_col, y_col: y_col},
                markers=True,
                template=template,
                color_discrete_sequence=[color]
            )

            # 5) Export to PNG in memory and send
            img_bytes = fig.to_image(format='png')
            return send_file(
                io.BytesIO(img_bytes),
                mimetype='image/png',
                download_name=f'plot-{idx}.png'
            )

        def send_ultramsg_image(to, image_url, caption=""):
            url = f"https://api.ultramsg.com/{self.ULTRAMSG_INSTANCE_ID}/messages/image"
            data = {
                "token": self.ULTRAMSG_TOKEN,
                "to": to,
                "image": image_url,
                "caption": caption,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            resp = requests.post(url, headers=headers, data=data)
            print("UltraMsg image sent:", resp.status_code, resp.text)

        def send_ultramsg_text(to, message):
            url = f"https://api.ultramsg.com/{self.ULTRAMSG_INSTANCE_ID}/messages/chat"
            data = {
                "token": self.ULTRAMSG_TOKEN,
                "to": to,
                "body": message,
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            resp = requests.post(url, headers=headers, data=data)
            print("UltraMsg text sent:", resp.status_code, resp.text)

        @server.route("/ultramsg-webhook", methods=["POST"])
        def handle_ultramsg_message():
            # 1) Parse JSON payload
            payload = request.get_json(force=True) or {}
            if payload.get("event_type") != "message_received":
                return "OK", 200

            msg = payload.get("data", {})
            sender = msg.get("from")
            body_raw = msg.get("body", "")

            # 2) Normalize
            norm = " ".join(body_raw.lower().split())
            print(f"[ULTRAMSG] from={sender!r}, norm={norm!r}")

            # 3) Try fuzzy match against FIELD_NAMES
            field_match = difflib.get_close_matches(norm, FIELD_NAMES, n=1, cutoff=0.6)
            if field_match:
                field = field_match[0]
                df = pd.read_csv(self.file_path, sep=self.sep)
                if field in df.columns:
                    val = df[field].iloc[-1]
                    send_ultramsg_text(to=sender, message=f"🔹 Latest {field}: {val}")
                else:
                    send_ultramsg_text(to=sender,
                                       message=f"❌ Field '{field}' not found.")
                return "OK", 200

            # 4) Build snapshot commands list and fuzzy‐match
            max_idx = len(self.predefined_plots) - 1
            commands = ["snapshot"] + [f"snapshot {i}" for i in range(max_idx + 1)]
            snap_match = difflib.get_close_matches(norm, commands, n=1, cutoff=0.75)
            if snap_match:
                cmd = snap_match[0].split()
                idx = int(cmd[1]) if len(cmd) > 1 else 0
                if 0 <= idx <= max_idx:
                    image_url = url_for("snapshot", idx=idx, _external=True)
                    send_ultramsg_image(
                        to=sender,
                        image_url=image_url,
                        caption=f"📸 Snapshot {idx}"
                    )
                else:
                    send_ultramsg_text(
                        to=sender,
                        message=f"❌ Snapshot index out of range (0–{max_idx})."
                    )
                return "OK", 200

            # 5) No match → help
            send_ultramsg_text(
                to=sender,
                message=(
                    "❓ Unknown command.\n"
                    " • Send any field name (e.g. 'T_A[K]', 'dTdt[K/min]').\n"
                    " • Or 'snapshot' / 'snapshot <n>'."
                )
            )
            return "OK", 200

        # Assemble the full application layout
        app.layout = html.Div([
            store,
            card_selector,
            status_container,
            predefined_graphs,
            custom_container,
            controls,
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

            #Style
            palette = px.colors.qualitative.Vivid
            template = 'ggplot2'
            color_cycle = cycle(palette)

            # Generate figures for each predefined plot
            figs = []
            for x_col, y_col in self.predefined_plots:
                color = next(color_cycle)
                fig = px.line(df, x=x_col, y=y_col, title=f"{y_col} vs {x_col}", labels={x_col: x_col, y_col: y_col},
                              markers=True, template=template, color_discrete_sequence=[color])
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
                color = next(color_cycle)
                fig = px.line(df, x=pair['x'], y=pair['y'], title=f"{pair['y']} vs {pair['x']}", labels={pair['x']: pair['x'], pair['y']: pair['y']}, markers=True, template=template, color_discrete_sequence=[color])
                fig.update_layout(uirevision='keep_zoom')
                custom_children.append(html.Div(dcc.Graph(figure=fig, config={'scrollZoom': True}), style={'borderRadius': '4px'}))

            # Return all updated components: predefined figures, status cards, and custom graphs
            return [*figs, cards, custom_children]

        # Display server URLs to console
        display_ip = get_local_ip() if host == '0.0.0.0' else host
        print("Dash app is running!")
        print(f"• Local:   http://127.0.0.1:{port}")
        print(f"• Network: http://{display_ip}:{port}")
        print(f"• Secret Key: {secret_key}")

        # Launch the Dash server
        app.run(host=host, port=port, debug=False, dev_tools_silence_routes_logging=True,threaded=True)

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
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
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