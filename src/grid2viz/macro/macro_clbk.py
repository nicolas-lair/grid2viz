from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from src.app import app
import plotly.graph_objects as go

from src.grid2kpi.manager import episode, make_episode, base_dir, indx, agent_ref
from src.grid2kpi.episode import observation_model
from src.grid2kpi.episode import actions_model
from src.grid2viz.utils.graph_utils import get_axis_relayout


# TODO add contant color code for ref and studied agent
# studied_color = {'primary': #color, 'secondary': #color}
# ref_color = {'primary': #color, 'secondary': #color}

@app.callback(
    Output("cumulated_rewards_timeserie", "figure"),
    [Input('store', 'cur_agent_log')],
    [State("cumulated_rewards_timeserie", "figure")]
)
def load_reward_data_scatter(cur_agent_log, figure):
    ref_episode_reward_trace = observation_model.get_ref_agent_rewards_trace(episode)
    studied_agent_reward_trace = observation_model.get_studied_agent_reward_trace(
        make_episode(base_dir, cur_agent_log, indx))

    figure['data'] = [*ref_episode_reward_trace, *studied_agent_reward_trace]
    figure['layout'] = {**figure['layout'],
                        'yaxis2': {'side': 'right', 'anchor': 'x', 'overlaying': 'y'}, }
    return figure


@app.callback(
    Output("agent_study_pie_chart", "figure"),
    [Input('store', 'cur_agent_log')],
    [State("agent_study_pie_chart", "figure")]
)
def load_reward_data_scatter(cur_agent_log, figure):
    new_episode = make_episode(base_dir, cur_agent_log, indx)
    nb_actions = new_episode.action_data[['action_line', 'action_subs']].sum()
    figure['data'] = [go.Pie(
        labels=["Actions on Lines", "Actions on Substations"],
        values=[nb_actions["action_line"], nb_actions["action_subs"]]
    )]
    return figure


@app.callback(
    Output("timeseries_table", "data"),
    [Input("cumulated_rewards_timeserie", "clickData")],
    [State("timeseries_table", "data")]
)
def add_timestamp(clickData, data):
    if data is None:
        data = []
    new_data = {"Timestamps": clickData["points"][0]["x"]}
    if new_data not in data:
        data.append(new_data)
    return data


@app.callback(
    [Output("usage_rate_graph_study", "relayoutData"),
     Output("action_timeserie", "relayoutData"),
     Output("overflow_graph_study", "relayoutData"), ],
    [Input("cumulated_rewards_timeserie", "relayoutData")]
)
def relayout_graphs(relayout_data):
    # filter out the second yaxis
    relayout_other_figures = {
        key: value for key, value in relayout_data.items() if "2" not in key}

    return relayout_other_figures, relayout_other_figures, relayout_other_figures


@app.callback(
    [Output("indicator_score_output", "children"),
     Output("indicator_nb_overflow", "children"),
     Output("indicator_nb_action", "children")],
    [Input('store', 'cur_agent_log')]
)
def update_nbs(cur_agent_log):
    new_episode = make_episode(base_dir, cur_agent_log, indx)
    score = new_episode.meta["cumulative_reward"]
    nb_overflow = observation_model.get_total_overflow_ts(new_episode)[
        "value"].sum()
    nb_action = new_episode.action_data[['action_line', 'action_subs']].sum(
        axis=1).sum()
    return round(score), nb_overflow, nb_action


@app.callback(
    Output("store", "cur_agent_log"),
    [Input('agent_log_selector', 'value')],
)
def update_agent_log(value):
    # hack to make sure the episode is loaded before all other callbcks descending agent_log_selector
    episode = make_episode(base_dir, value, indx)
    return value


@app.callback(
    [Output("overflow_graph_study", "figure"), Output(
        "usage_rate_graph_study", "figure")],
    [Input('store', 'cur_agent_log'),
     Input('cumulated_rewards_timeserie', 'relayoutData')],
    [State("overflow_graph_study", "figure"),
     State("usage_rate_graph_study", "figure")]
)
def update_agent_log_graph(cur_agent_log, relayout_data, figure_overflow, figure_usage):
    if relayout_data is not None and relayout_data != {'autosize': True}:
        layout_usage = figure_usage["layout"]
        new_axis_layout = get_axis_relayout(figure_usage, relayout_data)
        if new_axis_layout is not None:
            layout_usage.update(new_axis_layout)
            figure_overflow["layout"].update(new_axis_layout)
            return figure_overflow, figure_usage
    new_episode = make_episode(base_dir, cur_agent_log, indx)
    figure_overflow["data"] = observation_model.get_total_overflow_trace(
        new_episode)
    figure_usage["data"] = observation_model.get_usage_rate_trace(new_episode)
    return figure_overflow, figure_usage


@app.callback(
    Output("action_timeserie", "figure"),
    [Input('store', 'cur_agent_log'),
     Input('cumulated_rewards_timeserie', 'relayoutData')],
    [State("action_timeserie", "figure")]
)
def update_actions_graph(cur_agent_log, relayout_data, figure):
    if relayout_data is not None and relayout_data != {'autosize': True}:
        layout = figure["layout"]
        new_axis_layout = get_axis_relayout(figure, relayout_data)
        if new_axis_layout is not None:
            layout.update(new_axis_layout)
            return figure

    new_episode = make_episode(base_dir, cur_agent_log, indx)
    actions_ts = new_episode.action_data.set_index("timestamp")[[
        'action_line', 'action_subs'
    ]].sum(axis=1).to_frame(name="Nb Actions")
    ref_episode = make_episode(base_dir, agent_ref, indx)
    ref_agent_actions_ts = ref_episode.action_data.set_index("timestamp")[[
        'action_line', 'action_subs'
    ]].sum(axis=1).to_frame(name="Nb Actions")
    ref_action_details = action_tooltip(ref_episode.actions)
    new_action_details = action_tooltip(new_episode.actions)
    figure["data"] = [
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=actions_ts["Nb Actions"], name=cur_agent_log,
                   text=new_action_details),
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=ref_agent_actions_ts["Nb Actions"], name=agent_ref,
                   text=ref_action_details),

        go.Scatter(x=new_episode.action_data.timestamp,
                   y=new_episode.action_data["distance"], name=cur_agent_log + " distance", yaxis='y2'),
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=ref_episode.action_data["distance"], name=agent_ref + " distance", yaxis='y2'),
    ]
    figure['layout'] = {**figure['layout'],
                        'yaxis2': {'side': 'right', 'anchor': 'x', 'overlaying': 'y'}, }
    return figure


def action_tooltip(episode_actions):
    tooltip = []
    no_action_text = 'Do nothing'

    for action in episode_actions:
        impact_on_action = []
        detail = action.impact_on_objects()

        if detail['has_impact']:
            if detail['injection']['changed']:
                for injection in detail:
                    impact_on_action.append('\n injection set {} to {}'.format(injection['set'], injection['to']))

            if detail['force_line']['changed']:
                reconnections_count = detail['force_line']['reconnections']['count']
                if reconnections_count > 0:
                    impact_on_action.append('\n force reconnection of {} powerlines'
                                            .format(reconnections_count))

                disconnections_count = detail['force_line']['disconnections']['count']
                if disconnections_count > 0:
                    impact_on_action.append('\n force disconnection of {} powerlines'
                                            .format(disconnections_count))

            if detail['switch_line']['changed']:
                impact_on_action.append('switch status of {} powerlines'
                                        .format(detail['switch_line']['count']))

            if detail['topology']['changed']:
                bus_switchs = detail['topology']['bus_switch']
                assigned_bus = detail['topology']['assigned_bus']
                disconnected_bus = detail['topology']['disconnect_bus']

                if len(bus_switchs) > 0:
                    for bus_switch in bus_switchs:
                        impact_on_action.append('\n switch bus of {} {} on substation {}'
                                                .format(bus_switch['object_type'],
                                                        bus_switch['object_id'],
                                                        bus_switch['substation']))
                if len(assigned_bus) > 0:
                    for assigned in assigned_bus:
                        impact_on_action.append('\n assign bus {} to {} {} on substation {}'
                                                .format(assigned['bus'], assigned['object_type'],
                                                        assigned['object_id'], assigned['substation']))
                if len(disconnected_bus) > 0:
                    for disconnected in disconnected_bus:
                        impact_on_action.append('\n disconnect bus {} {} on substation {}'
                                                .format(disconnected['object_type'],
                                                        disconnected['object_id'],
                                                        disconnected['substation']))

            tooltip.append(''.join(impact_on_action))

        else:
            tooltip.append(no_action_text)

    return tooltip


@app.callback(
    [Output("inspector_datable", "columns"),
     Output("inspector_datable", "data")],
    [Input('store', 'cur_agent_log')],
    [State("inspector_datable", "data")]
)
def update_agent_log_action_table(cur_agent_log, data):
    new_episode = make_episode(base_dir, cur_agent_log, indx)
    table = actions_model.get_action_table_data(new_episode)
    return [{"name": i, "id": i} for i in table.columns], table.to_dict("record")


@app.callback(
    [Output("distribution_substation_action_chart", "figure"),
     Output("distribution_line_action_chart", "figure")],
    [Input('store', 'cur_agent_log')],
    [State("distribution_substation_action_chart", "figure"),
     State("distribution_line_action_chart", "figure")]
)
def update_agent_log_action_graphs(cur_agent_log, figure_sub, figure_switch_line):
    new_episode = make_episode(base_dir, cur_agent_log, indx)
    figure_sub["data"] = actions_model.get_action_per_sub(new_episode)
    # figure_line["data"] = actions_model.get_action_set_line_trace(new_episode)
    # figure_bus["data"] = actions_model.get_action_change_bus_trace(new_episode)
    figure_switch_line["data"] = actions_model.get_action_switch_line_trace(
        new_episode)
    return figure_sub, figure_switch_line
