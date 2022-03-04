import numpy as np
import tensorflow as tf
import os
import model
import json
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.animation as animation
from visualize_traj import animate
from model import LR

N_EPISODES = 3
C          = 1
M          = 1
GAMMA      = 0.8
VMAX       = 1.0 #??
#TODO: add epsilon greedy

USER = 'Brian'
# USER = 'Torstein'
# USER = 'Valentin'
# USER = 'Bradley'

if USER == 'Torstein':
    folder = "/home/torstein/Stanford/aa277/aa277_project/data"
elif USER == 'Brian':
    folder  = "/home/bdobkowski/Stanford/AA277/aa277_project/data"
else:
    raise Exception('Need to list a folder in on your local machine to store data')

def load_training_test_data(folder):
    with open(os.path.join(folder, 'x_dict.json'), 'r') as j:
        x_dict = json.loads(j.read())
    with open(os.path.join(folder, 'y_dict.json'), 'r') as j:
        y_dict = json.loads(j.read())
    
    for xk, yk in zip(x_dict.keys(), y_dict.keys()):
        x_dict[xk] = np.asarray(x_dict[xk])
        y_dict[yk] = np.asarray(y_dict[yk])

    return x_dict, y_dict

def propagate_dynamics(x, v, dt):
    '''
       Single integrator robot dynamics
    '''

    # TODO: incorporate kinematic constraints?

    try:
        a, b = x.shape
        x[:, 0:2] = x[:, 0:2] + dt* v
        return x
    except:
        x[0:2] = x[0:2] + dt* v
        return x

def get_goal(x):
    try:
        a, b = x.shape
        return x[5:7, -1]
    except:
        return x[5:7]

def get_pos(x):
    try:
        a, b = x.shape
        return x[0:2, -1]
    except:
        return x[0:2]

def get_vel(x):
    try:
        a, b = x.shape
        return x[2:4, -1]
    except:
        return x[2:4]

def get_vpref(x):
    try:
        a, b = x.shape
        return x[7, -1]
    except:
        return x[7]

def get_radius(x):
    try:
        a, b = x.shape
        return x[4, -1]
    except:
        return x[4]

def get_current_state(x):
    return np.copy(x[:, -1])

def reward(x1, x2, a, dt):
    '''
    Reward function for robot 1 only, given joint state (parametrized by 2 individual states)
    '''
    x2_const_vel = get_vel(x2)

    # below adapted from public CADRL repo
    dmin = float('inf')
    dmin_time = 1
    for frac in np.linspace(0, 1, num=5):
        time = frac*dt
        x1_pos = get_pos(propagate_dynamics(x1, a, time))
        x2_pos = get_pos(propagate_dynamics(x2, x2_const_vel, time))
        distance = np.linalg.norm(x1_pos - x2_pos)
        if distance < dmin:
            dmin = distance
            dmin_time = time

    x1_nxt = propagate_dynamics(x1, a, dt)

    if dmin < get_radius(x1) + get_radius(x2):
        R = -0.25
        end_time = dmin_time
    else:
        end_time = 1
        if dmin < get_radius(x1) + get_radius(x2) + 0.2:
            R = -0.1 - dmin/2
        elif close_to_goal(x1_nxt):
            R = 1
        else:
            R = 0

    return R

def close_to_goal(x):
    '''
    condition for exiting the while loop in CADRL
    '''
    return np.linalg.norm(get_pos(x) - get_goal(x)) < 1e-1

def plot_animation(Pg1, Pg2, X_robo1, X_robo2, radius1, radius2):
    fig = plt.figure()
    ax1 = fig.add_subplot(1,1,1)
    xlimits = [-5,5]
    ylimits = [-2.5, 2.5]
    ax1.set_xlim(xlimits)
    ax1.set_ylim(ylimits)

    if len(X_robo1) > len(X_robo2):
        x2 = np.zeros((len(X_robo1), 2))
        x2[0:len(X_robo2)] = X_robo2
        x2[len(X_robo2):] = X_robo2[-1]
        x1 = X_robo1
    elif len(X_robo2) > len(X_robo1):
        x1 = np.zeros((len(X_robo2), 2))
        x1[0:len(X_robo1)] = X_robo1
        x1[len(X_robo1):] = X_robo1[-1]
        x2 = X_robo2
    else:
        x1 = X_robo1
        x2 = X_robo2

    anim = FuncAnimation(fig, animate, interval=100, fargs=(Pg1,
            Pg2,
            x1,
            x2,
            radius1,
            radius2,
            ax1))
    pth = os.path.join(folder, 'dummy.mp4')
    writervideo = animation.FFMpegWriter(fps=20) 
    anim.save(pth, writer=writervideo)
    plt.show()

def create_train_set_from_dict(x_dict, y_dict):

    dim_rot_joint_state = 15
    xs = np.array([]).reshape((0, dim_rot_joint_state))
    ys = np.array([])

    for xk, yk in zip(x_dict.keys(), y_dict.keys()):

        x1_joint = model.get_joint_state_vectorized(x_dict[xk][0], x_dict[xk][1])
        x2_joint = model.get_joint_state_vectorized(x_dict[xk][1], x_dict[xk][0])

        x1_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x1_joint)
        x2_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x2_joint)

        xs = np.vstack([xs, x1_joint_rotated])
        xs = np.vstack([xs, x2_joint_rotated])

        try:
            ys = np.concatenate((ys, y_dict[yk][0]))
            ys = np.concatenate((ys, y_dict[yk][1]))
        except:
            ys = np.concatenate((ys, y_dict[yk][0].numpy().flatten()))
            ys = np.concatenate((ys, y_dict[yk][1].numpy().flatten()))

    return xs, ys

def CADRL(value_model, initial_state_1, initial_state_2):
    '''
        Algorithm 1: CADRL (Collision Avoidance with Deep RL)

        INCOMPLETE

        Doesn't work yet. Also haven't implemented epsilon-greedy exploration yet
    '''
    dt = 0.1 # uncertain
    t  = 0

    # robot trajectories will be 9xT, where T is the total timesteps in the traj
    x_1 = initial_state_1.reshape(-1, 1) # robot 1 state px, py, vx, vy, ...
    x_2 = initial_state_2.reshape(-1, 1) # robot 2 state px, py, vx, vy, ...

    state_dim = initial_state_1.shape[0]

    # x[0:2] - position
    # x[2:4] - velocity
    # x[5:7] - goal position

    # while distance between robots and there goals is greater than eps
    while (not close_to_goal(x_1)) or (not close_to_goal(x_2)):
        t += dt

        n_timesteps_x1 = len(x_1[0])
        n_timesteps_x2 = len(x_2[0])

        v_filtered_1 = np.ma.average(x_1[2:4, :], axis=1, weights = np.exp(range(n_timesteps_x1))) # weights the more recent scores more
        v_filtered_2 = np.ma.average(x_2[2:4, :], axis=1, weights = np.exp(range(n_timesteps_x2))) # weights the more recent scores more

        # Question: how do we set the velocities for the ~ robot in CADRL?
        # My feeling is we do both robots in CADRL simultaneously
        # To do this, I think we'd need to save and load states for individual robots 
        # rather than loading joint states/trajectories
        x1_o_nxt = propagate_dynamics(get_current_state(x_1), v_filtered_1, dt)
        x2_o_nxt = propagate_dynamics(get_current_state(x_2), v_filtered_2, dt)

        num_sampled_actions = 50

        A = np.random.uniform(low=-VMAX, high=VMAX, size=(num_sampled_actions-1, 2)) # TODO: how should we sample actions?
        A = np.append(A, np.array([[0, 0]]), axis=0)

        gamma_bar_x1 = GAMMA**dt*get_vpref(x_1)
        gamma_bar_x2 = GAMMA**dt*get_vpref(x_2)

        x1_nxt = np.zeros((num_sampled_actions, state_dim))
        x2_nxt = np.zeros((num_sampled_actions, state_dim))

        lookahead_1 = np.zeros(num_sampled_actions)
        lookahead_2 = np.zeros(num_sampled_actions)

        # attempt at vectorizing this A loop

        # curr_state_1 = np.repeat(get_current_state(x_1), repeats=num_sampled_actions, axis=0)
        # curr_state_2 = np.repeat(get_current_state(x_2), repeats=num_sampled_actions, axis=0)

        # x1_nxt = propagate_dynamics(curr_state_1, A, dt)
        # x2_nxt = propagate_dynamics(curr_state_2, A, dt)

        # x1_joint = model.get_joint_state_vectorized(s_1, s_2)
        # x2_joint = model.get_joint_state_vectorized(s_2, s_1)

        # x1_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x1_joint)
        # x2_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x2_joint)

        for idx, a in enumerate(A):
            x1_nxt[idx] = propagate_dynamics(get_current_state(x_1), a, dt)
            x2_nxt[idx] = propagate_dynamics(get_current_state(x_2), a, dt)

            x1_joint = model.get_joint_state2(x1_nxt[idx], x2_o_nxt)
            x2_joint = model.get_joint_state2(x2_nxt[idx], x1_o_nxt)

            x1_joint_rotated = model.get_rotated_state(x1_joint)
            x2_joint_rotated = model.get_rotated_state(x2_joint)

            # does our action have no impact on reward here? should we feed it the propagated state?
            R1 = reward(get_current_state(x_1), get_current_state(x_2), a, dt)
            R2 = reward(get_current_state(x_2), get_current_state(x_1), a, dt)

            lookahead_1[idx] = R1 + gamma_bar_x1 * value_model(x1_joint_rotated.reshape(1,-1))
            lookahead_2[idx] = R2 + gamma_bar_x2 * value_model(x2_joint_rotated.reshape(1,-1))

        opt_action_1 = A[np.argmax(lookahead_1)]
        opt_action_2 = A[np.argmax(lookahead_2)]

        if not close_to_goal(x_1):        
            x_1 = np.append(x_1, propagate_dynamics(get_current_state(x_1), opt_action_1, dt).reshape(-1, 1), axis=1)
        if not close_to_goal(x_2):
            x_2 = np.append(x_2, propagate_dynamics(get_current_state(x_2), opt_action_2, dt).reshape(-1, 1), axis=1)

        print(np.linalg.norm(get_pos(x_1) - get_goal(x_1)))
        # print(np.linalg.norm(get_pos(x_2) - get_goal(x_2)))

        if n_timesteps_x1 > 75 or n_timesteps_x2 > 75:

            plot_animation(get_goal(x_1),
                           get_goal(x_2),
                           x_1[0:2, :].T,
                           x_2[0:2, :].T,
                           get_radius(x_1),
                           get_radius(x_2))

            return x_1.T, x_2.T, False

    plot_animation(get_goal(x_1),
                   get_goal(x_2),
                   x_1[0:2, :].T,
                   x_2[0:2, :].T,
                   get_radius(x_1),
                   get_radius(x_2))

    return x_1.T, x_2.T, True

def loss(y_est, y):
    '''
    MSE loss
    '''
    shape_y = tf.cast(tf.shape(y), dtype=tf.float32)
    return tf.divide(tf.reduce_sum(tf.square(y_est - y)), shape_y[0])

if __name__ == '__main__':

    optimizer = tf.keras.optimizers.SGD(learning_rate=LR, momentum=0.9)

    # algorithm 2 line 4
    value_model = tf.keras.models.load_model(os.path.join(folder, 'initial_value_model'))
    value_model_prime = value_model

    # algorithm 2 line 5
    # x_dict, y_dict = load_training_test_data(folder)
    x_ep_dict, y_ep_dict = model.load_traj_generate_data_not_joint(folder)

    x_experience = x_ep_dict.copy()
    y_experience = y_ep_dict.copy()

    # x_ep_dict is a dictionary with following pattern:
    # x_ep_dict[1] is all robot traj data for episode 1
    # x_ep_dict[1][2] is robot 2 traj data for episode 1
    # x_ep_dict[1][2][3] is timestep 3 for robot 2 in episode 1
    # x_ep_dict[1][2][3] is 10-dimensional, and contains the state from get_state() in model.py

    # y_ep_dict is constructed the same way

    for training_ep in range(N_EPISODES):
        for m in range(M):

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
            print(f'Random robot 1: {rand_idx_1}')
            print(f'Random robot 2: {rand_idx_2}')

            # s_1, s_2 are Tx9, 9 being the state dimension
            s_1, s_2, cadrl_successful = CADRL(value_model, s_initial_1, s_initial_2)

            if cadrl_successful:

                print('CADRL Successful!')

                # trajectories s1 and s2 are different lengths
                x1_joint = model.get_joint_state_vectorized(s_1, s_2)
                x2_joint = model.get_joint_state_vectorized(s_2, s_1)

                x1_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x1_joint)
                x2_joint_rotated = np.apply_along_axis(model.get_rotated_state, 1, x2_joint)
                
                # algorithm 2 line 10
                y_1 = value_model_prime(x1_joint_rotated)
                y_2 = value_model_prime(x2_joint_rotated)

                # algorithm 2 line 11
                x_experience[rand_ep][rand_idx_1] = s_1
                x_experience[rand_ep][rand_idx_2] = s_2
                y_experience[rand_ep][rand_idx_1] = y_1
                y_experience[rand_ep][rand_idx_2] = y_2

        # algorithm 2 line 12
        x_train, y_train = create_train_set_from_dict(x_experience, y_experience)
        n_entries = x_train.shape[0]
        subset_idx = np.random.choice(n_entries, int(np.floor(n_entries/4)), replace=False)

        # algorithm 2 line 13
        with tf.GradientTape() as tape:
            y_est = value_model(x_train[subset_idx])
            current_loss = loss(y_est, y_train[subset_idx].reshape(-1,1))  
        grads = tape.gradient(current_loss, value_model.trainable_weights)  
        optimizer.apply_gradients(zip(grads, value_model.trainable_weights)) 

        # algorithm 2 line 14-15
        if np.mod(training_ep, C) == 0:
            # evaluate value model here...
            value_model_prime = value_model

    value_model.save(os.path.join(folder, 'post_RL_value_model'))
