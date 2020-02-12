import datetime as dt
import time

from grid2op.EpisodeData import EpisodeData
import numpy as np
import pandas as pd
from tqdm import tqdm

from . import EpisodeTrace


class EpisodeAnalytics:
    def __init__(self, episode_data, episode_name, agent):
        self.episode_name = episode_name
        self.agent = agent

        # Add EpisodeData attributes to EpisodeAnalytics 
        for attribute in [elem for elem in dir(episode_data) if
                          not (elem.startswith("__") or callable(getattr(episode_data, elem)))]:
            setattr(self, attribute, getattr(episode_data, attribute))
        print("computing df")
        beg = time.time()
        print("Environment")
        self.load, self.production, self.rho, self.action_data, self.action_data_table, self.computed_reward, self.flow_and_voltage_line = self._make_df_from_data()
        print("Hazards-Maintenances")
        self.hazards, self.maintenances = self._env_actions_as_df()
        print("Big TS")
        self.total_overflow_trace = EpisodeTrace.get_total_overflow_trace(self)
        self.usage_rate_trace = EpisodeTrace.get_usage_rate_trace(self)
        self.reward_trace = EpisodeTrace.get_df_rewards_trace(self)
        self.total_overflow_ts = EpisodeTrace.get_total_overflow_ts(self)
        end = time.time()
        print(f"end computing df: {end - beg}")

    @staticmethod
    def timestamp(obs):
        return dt.datetime(obs.year, obs.month, obs.day, obs.hour_of_day,
                           obs.minute_of_hour)

    # @jit(forceobj=True)
    def _make_df_from_data(self):
        size = len(self.actions)
        load_size = size * len(self.observations[0].load_p)
        prod_size = size * len(self.observations[0].prod_p)
        rho_size = size * len(self.observations[0].rho)
        flow_voltage_cols = ["timestep", "timestamp", "equipement_id", "equipment_name",
                "value"]
        load_data = pd.DataFrame(index=range(load_size), columns=flow_voltage_cols)
        production = pd.DataFrame(index=range(prod_size), columns=flow_voltage_cols)
        rho = pd.DataFrame(index=range(rho_size), columns=[
            'time', "timestamp", 'equipment', 'value'])

        cols_loop_action_data = ['action_line', 'action_subs', 'set_line', 'switch_line',
                                 'set_topo', 'change_bus', 'distance']
        action_data = pd.DataFrame(
            index=range(size),
            columns=[
                'timestep', 'timestamp', 'timestep_reward', 'action_line',
                'action_subs', 'set_line', 'switch_line', 'set_topo',
                'change_bus', 'distance'
            ]
        )

        cols_loop_action_data_table = [
            'action_line', 'action_subs', 'line_action', 'sub_name',
            'objects_changed', 'distance'
        ]
        action_data_table = pd.DataFrame(
            index=range(size),
            columns=[
                'timestep', 'timestamp', 'timestep_reward', 'action_line',
                'action_subs', 'line_action', 'sub_name', 'objects_changed',
                'distance'
            ]
        )

        computed_rewards = pd.DataFrame(index=range(size),
                                        columns=['timestep', 'rewards', 'cum_rewards'])
        flow_voltage_cols = pd.MultiIndex.from_product(
            [['or', 'ex'], ['active', 'reactive', 'current', 'voltage'], self.line_names])
        flow_voltage_line_table = pd.DataFrame(index=range(size), columns=flow_voltage_cols)

        topo_list = []
        bus_list = []
        for (time_step, (obs, act)) in tqdm(enumerate(zip(self.observations[:-1], self.actions)),
                                            total=len(self.env_actions)):
            time_stamp = self.timestamp(obs)
            line_impact, sub_impact = act.get_topological_impact()
            sub_action = act.name_sub[sub_impact]  # self.get_sub_action(act, obs)

            if not len(sub_action):
                sub_action = None

            line_action = ""
            open_status = np.where(act._set_line_status == 1)
            close_status = np.where(act._set_line_status == -1)
            switch_line = np.where(act._switch_line_status is True)

            if len(open_status[0]) == 1:
                line_action = "connect ".join(str(self.line_names[open_status[0]]))
            if len(close_status[0]) == 1:
                line_action = "disconnect ".join(str(self.line_names[close_status[0]]))
            if len(switch_line[0]) == 1:
                line_action = "switch ".join(str(self.line_names[switch_line[0]]))

            for equipment_id, load_p in enumerate(obs.load_p):
                pos = time_step * self.n_loads + equipment_id
                load_data.loc[pos, :] = [
                    time_step, time_stamp, equipment_id,
                    self.load_names[equipment_id], load_p]

            for equipment_id, prod_p in enumerate(obs.prod_p):
                pos = time_step * self.n_prods + equipment_id
                production.loc[pos, :] = [
                    time_step, time_stamp, equipment_id,
                    self.prod_names[equipment_id], prod_p]

            for equipment, rho_t in enumerate(obs.rho):
                pos = time_step * len(obs.rho) + equipment
                rho.loc[pos, :] = [time_step, time_stamp, equipment, rho_t]

            for line, subs in zip(range(act.n_line), range(len(act.sub_info))):
                pos = time_step
                action_line = np.sum(act._switch_line_status)

                # TODO: change temporary fix below
                action_subs = int(np.any(act._change_bus_vect))

                action_data.loc[pos, cols_loop_action_data] = [
                    action_line,
                    action_subs,
                    act._set_line_status.flatten().astype(np.float),
                    act._switch_line_status.flatten().astype(np.float),
                    act._set_topo_vect.flatten().astype(np.float),
                    act._change_bus_vect.flatten().astype(np.float),
                    self.get_distance_from_obs(obs)]
                object_changed_set = self.get_object_changed(
                    act._set_topo_vect, topo_list)
                if object_changed_set is not None:
                    object_changed = object_changed_set
                else:
                    object_changed = self.get_object_changed(
                        act._change_bus_vect, bus_list)
                action_data_table.loc[pos, cols_loop_action_data_table] = [
                    action_line,
                    action_subs,
                    line_action,
                    sub_action,
                    object_changed,
                    self.get_distance_from_obs(obs)]

            computed_rewards.loc[time_step, :] = [
                time_stamp,
                self.rewards[time_step],
                self.rewards.cumsum(axis=0)[time_step]
            ]

            flow_voltage_line_table.loc[time_step, :] = np.array([
                obs.p_ex,
                obs.q_ex,
                obs.a_ex,
                obs.v_ex,
                obs.p_or,
                obs.q_or,
                obs.a_or,
                obs.v_or
            ]).flatten()

        self.timestamps = sorted(load_data.timestamp.dropna().unique())
        self.timesteps = sorted(load_data.timestep.unique())
        action_data["timestep"] = self.timesteps
        action_data["timestamp"] = self.timestamps
        action_data["timestep_reward"] = self.rewards[:size]
        action_data_table["timestep"] = self.timesteps
        action_data_table["timestamp"] = self.timestamps
        action_data_table["timestep_reward"] = self.rewards[:size]

        load_data["value"] = load_data["value"].astype(float)
        production["value"] = production["value"].astype(float)
        rho["value"] = rho["value"].astype(float)
        return load_data, production, rho, action_data, action_data_table, computed_rewards, flow_voltage_line_table

    def get_object_changed(self, vect, list_topo):
        if np.count_nonzero(vect) is 0:
            return None
        for idx, topo_array in enumerate(list_topo):
            if not np.array_equal(topo_array, vect):
                return idx
        # if we havnt found the vect...
        list_topo.append(vect)
        return len(list_topo) - 1

    def get_sub_action(self, act, obs):
        for sub in range(len(obs.sub_info)):
            effect = act.effect_on(substation_id=sub)
            if np.any(effect["change_bus"] is True):
                return self.name_sub[sub]
            if np.any(effect["set_bus"] is 1) or np.any(effect["set_bus"] is -1):
                return self.name_sub[sub]
        return None

    def get_distance_from_obs(self, obs):
        return len(obs.topo_vect) - np.count_nonzero(obs.topo_vect == 1)

    # @jit(forceobj=True)
    def _env_actions_as_df(self):
        hazards_size = (len(self.observations) - 1) * self.n_lines
        cols = ["timestep", "timestamp", "line_id", "line_name", "value"]
        hazards = pd.DataFrame(index=range(hazards_size), columns=cols)
        maintenances = hazards.copy()

        for (time_step, env_act) in tqdm(enumerate(self.env_actions), total=len(self.env_actions)):
            if env_act is None:
                continue
            time_stamp = self.timestamp(self.observations[time_step])
            iter_haz_maint = zip(env_act._hazards, env_act._maintenance)
            for line_id, (haz, maint) in enumerate(iter_haz_maint):
                pos = time_step * self.n_lines + line_id
                hazards.loc[pos, :] = [
                    time_step, time_stamp, line_id, self.line_names[line_id],
                    int(haz)
                ]
                maintenances.loc[pos, :] = [
                    time_step, time_stamp, line_id, self.line_names[line_id],
                    int(maint)
                ]
        hazards["value"] = hazards["value"].fillna(0).astype(int)
        maintenances["value"] = maintenances["value"].fillna(0).astype(int)
        return hazards, maintenances


class Test():
    def __init__(self):
        self.foo = 2
        self.bar = 3


if __name__ == "__main__":
    test = Test()
    path_agent = "nodisc_badagent"
    episode = EpisodeData.from_disk(
        "D:/Projects/RTE - Grid2Viz/20200127_data_scripts/20200127_agents_log/" + path_agent, "3_with_hazards")
    print(dir(EpisodeAnalytics(episode)))
