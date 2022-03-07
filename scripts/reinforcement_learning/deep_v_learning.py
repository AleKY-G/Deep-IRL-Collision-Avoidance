from re import sub
import numpy as np
import tensorflow as tf
import os
import model
import random

from cadrl import CADRL
from state_definitions import  get_joint_state, get_joint_state_vectorized, get_rotated_state, get_state
from nn_utils import get_nn_input, load_traj_data, create_train_set_from_dict, load_nn_data
from rl_utils import  get_vpref, find_y_values
from model import LR, USER, FOLDER, backprop
from configs import *
from tqdm import tqdm






if __name__ == '__main__':

    optimizer = tf.keras.optimizers.SGD(learning_rate=LR, momentum=0.9)

    # algorithm 2 line 4
    value_model = tf.keras.models.load_model(os.path.join(FOLDER, 'initial_value_model'))
    V_prime = value_model

    # algorithm 2 line 5
    # x_dict, y_dict = load_training_test_data(folder)
    x_ep_dict, v_pref, dt = load_traj_data(FOLDER)
    x_dict_rotated, y_ep_dict = get_nn_input(x_ep_dict, v_pref, dt)

    x_experience = x_dict_rotated.copy()
    y_experience = y_ep_dict.copy()

    # x_ep_dict is a dictionary with following pattern:
    # x_ep_dict[1] is all robot traj data for episode 1
    # x_ep_dict[1][2] is robot 2 traj data for episode 1
    # x_ep_dict[1][2][3] is timestep 3 for robot 2 in episode 1
    # x_ep_dict[1][2][3] is 10-dimensional, and contains the state from get_state() in model.py

    # y_ep_dict is constructed the same way

    for training_ep in range(N_EPISODES):

        print(f'\n====== Episode {training_ep} ======\n')

        m = 0
        while m != M-1:
        
            rand_ep = np.random.randint(0, high=len(x_ep_dict.keys()))
            
            # algorithm 2 line 8: random test case (by index)
            rand_idx_1 = np.random.randint(0, high=len(x_ep_dict[rand_ep].keys()))
            rand_idx_2 = np.random.randint(0, high=len(x_ep_dict[rand_ep].keys()))
            while rand_idx_2 == rand_idx_1:
                rand_idx_2 = np.random.randint(0, high=len(x_ep_dict[rand_ep].keys()))

            # FOR TESTING ONLY
            # rand_ep = 74
            # rand_idx_1 = 1
            # rand_idx_2 = 0

            # algorithm 2 line 9
            # should we be choosing data from experience set or dataset here?
            s_initial_1 = x_ep_dict[rand_ep][rand_idx_1][0]
            s_initial_2 = x_ep_dict[rand_ep][rand_idx_2][0]
            print(f'Random episode: {rand_ep}')
            # print(f'Random robot 1: {rand_idx_1}')
            # print(f'Random robot 2: {rand_idx_2}')

            # s_1, s_2 are Tx9, 9 being the state dimension
            s_1, s_2, cadrl_successful, Rs1, Rs2, x1s_rot, x2s_rot = CADRL(value_model, s_initial_1, s_initial_2, EPS_GREEDY, DT, episode=training_ep)

            if cadrl_successful:
                m+=1
                print(f"CADRL Successful! {s_1.shape[0]}, {s_2.shape[0]}")

                # trajectories s1 and s2 are different lengths
                # x1_joint = model.get_joint_state_vectorized(s_1, s_2)
                # x2_joint = model.get_joint_state_vectorized(s_2, s_1)

                # x1_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x1_joint)
                # x2_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x2_joint)
                
                # algorithm 2 line 10
                # this is not done correctly, we have to actually back out the values for gamma^tg*vpref
                xs_rot1, y_1 = find_y_values(V_prime, x1s_rot, x2s_rot, Rs1, GAMMA)
                xs_rot2, y_2 = find_y_values(V_prime, x2s_rot, x1s_rot, Rs2, GAMMA)

                # need to implement this function - it's empty now
                assert(y_1.shape[0] == xs_rot1.shape[0] 
                and y_2.shape[0] == xs_rot2.shape[0]), "xsrot not same shape as y_1"
                # algorithm 2 line 11
                x_experience[rand_ep][rand_idx_1] = xs_rot1
                x_experience[rand_ep][rand_idx_2] = xs_rot2
                y_experience[rand_ep][rand_idx_1] = y_1
                y_experience[rand_ep][rand_idx_2] = y_2

        # algorithm 2 line 12
        #x_train, y_train = create_train_set_from_dict(x_experience, y_experience)

        x_train, y_train, _, _ = load_nn_data(x_experience, y_experience)
        n_entries = x_train.shape[0]

        # algorithm 2 line 13
        # this is only one training step, we need to do this for many epochs across the whole dataset ## "Not the whole dataset?"
        # Torstein, can you help with this part?
        subset_idx = np.random.choice(n_entries, int(np.floor(n_entries*RL_BATCH_FRAC)), replace=False)
        subset = x_train[subset_idx]

        backprop(value_model, x_train[subset_idx], y_train[subset_idx], NUM_RL_EPOCHS)

        # algorithm 2 line 14-15
        if np.mod(training_ep, C) == 0:
            # evaluate value model here...
            value_model_prime = value_model

    value_model.save(os.path.join(FOLDER, 'post_RL_value_model'))
