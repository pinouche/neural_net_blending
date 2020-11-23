import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import log_loss, accuracy_score
from scipy.special import softmax
import pickle
import keras
import copy
import random


# load data functions
def unpickle(file):
    with open(file, 'rb') as fo:
        data_dict = pickle.load(fo, encoding='bytes')
    return data_dict


def load_mnist(flatten=True):
    (x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()
    x_train, x_test = x_train / 255.0, x_test / 255.0

    if flatten:
        x_train = np.reshape(x_train, (x_train.shape[0], 28 * 28))
        x_test = np.reshape(x_test, (x_test.shape[0], 28 * 28))

    return x_train, x_test, y_train, y_test


def load_cifar_100(flatten=True):
    (x_train, y_train), (x_test, y_test) = keras.datasets.cifar100.load_data(label_mode="coarse")
    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')

    x_train = x_train / 255.0
    x_test = x_test / 255.0

    if flatten:
        x_train = np.reshape(x_train, (x_train.shape[0], 3072))
        x_test = np.reshape(x_test, (x_test.shape[0], 3072))

    return x_train, x_test, y_train, y_test


def load_cifar(flatten=True):
    (x_train, y_train), (x_test, y_test) = keras.datasets.cifar10.load_data()
    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')

    x_train = x_train / 255.0
    x_test = x_test / 255.0

    if flatten:
        x_train = np.reshape(x_train, (x_train.shape[0], 3072))
        x_test = np.reshape(x_test, (x_test.shape[0], 3072))

    return x_train, x_test, y_train, y_test


def partition_classes(x_train, x_test, y_train, y_test, cut_off=0.5):
    cut_off = int(len(np.unique(y_train)) * cut_off)

    mask_train = np.squeeze(y_train >= cut_off)
    mask_test = np.squeeze(y_test >= cut_off)

    x_train_s1 = x_train[mask_train]
    y_train_s1 = y_train[mask_train]
    x_test_s1 = x_test[mask_test]
    y_test_s1 = y_test[mask_test]

    x_train_s2 = x_train[~mask_train]
    y_train_s2 = y_train[~mask_train]
    x_test_s2 = x_test[~mask_test]
    y_test_s2 = y_test[~mask_test]

    return x_train_s1, y_train_s1, x_test_s1, y_test_s1, x_train_s2, y_train_s2, x_test_s2, y_test_s2


def get_hidden_layers(model, data_x, batch_size):
    data_x = data_x[:batch_size]

    def keras_function_layer(model_layer, data):
        hidden_func = keras.backend.function(model.layers[0].input, model_layer.output)
        result = hidden_func([data])

        return result

    hidden_layers_list = []
    for index in range(len(model.layers)):
        if isinstance(model.layers[index], keras.layers.convolutional.Conv2D) or isinstance(model.layers[index],
                                                                                            keras.layers.Dense):
            hidden_layer = keras_function_layer(model.layers[index], data_x)
            hidden_layers_list.append(hidden_layer)

    return hidden_layers_list


def compute_neurons_variance(hidden_layers_list):
    list_variance_filters = []

    for layer_id in range(len(hidden_layers_list) - 1):

        batch_size = hidden_layers_list[layer_id].shape[0]
        size_activation_map = hidden_layers_list[layer_id].shape[1]

        # draw a random value from each of the CNN filters
        i_dim = np.random.choice(range(0, size_activation_map), batch_size)
        j_dim = np.random.choice(range(0, size_activation_map), batch_size)

        layer_one = []
        for index in range(batch_size):
            layer_one.append(hidden_layers_list[layer_id][index][i_dim[index], j_dim[index], :])

        variance = np.var(np.array(layer_one), axis=0)
        list_variance_filters.append(variance)

    return list_variance_filters


def identify_interesting_neurons(list_cross_corr, list_self_corr, q_value_list):

    neurons_indices_list_worst_parent = []
    indices_neurons_non_converged_best_parent_list = []

    for index in range(len(list_cross_corr)):

        print(q_value_list[index])

        self_corr = copy.deepcopy(list_self_corr[index])
        self_corr = np.abs(self_corr)
        np.fill_diagonal(self_corr, -0.1)

        num_filters = self_corr.shape[0]
        num_neurons_to_remove = int(num_filters * q_value_list[index])
        list_neurons_remove = []
        for _ in range(num_neurons_to_remove):
            index_remove = np.argmax(np.max(self_corr, axis=1))
            self_corr = np.delete(self_corr, index_remove, 0)
            self_corr = np.delete(self_corr, index_remove, 1)

            list_neurons_remove.append(index_remove)

        num_neurons_to_remove = len(list_neurons_remove)

        bool_idx = np.ones(num_filters, dtype=bool)
        bool_idx[list_neurons_remove] = False
        corr_matrix = copy.deepcopy(list_cross_corr[index][bool_idx])

        max_corr_list = []
        for j in range(corr_matrix.shape[1]):
            corr = np.abs(corr_matrix[:, j])
            max_corr = np.max(corr)
            max_corr_list.append((max_corr, j))
        max_corr_list.sort()
        print(max_corr_list)
        indices = [tuples[1] for tuples in max_corr_list[:num_neurons_to_remove]]

        neurons_indices_list_worst_parent.append(indices)
        indices_neurons_non_converged_best_parent_list.append(list_neurons_remove)

    return neurons_indices_list_worst_parent, indices_neurons_non_converged_best_parent_list


def match_random_filters(q_value_list):
    filters_to_remove = []
    filters_to_transplant = []

    for index in range(len(q_value_list)):
        num_filters = len(q_value_list[index])
        num_filters_to_change = int(num_filters * q_value_list[index])
        indices_to_remove = random.sample(range(num_filters), num_filters_to_change)
        indices_to_transplant = random.sample(range(num_filters), num_filters_to_change)

        filters_to_remove.append(indices_to_remove)
        filters_to_transplant.append(indices_to_transplant)

    return filters_to_transplant, filters_to_remove


# def compute_mask_convergence(variance, q_variance):
#     mask_list = []
#
#     for layer in range(len(variance)):
#         var_layer = variance[layer]
#         mask_layer = var_layer <= np.quantile(var_layer, q_variance)
#
#         mask_list.append(mask_layer)
#
#     return mask_list


def get_corr_cnn_filters(hidden_representation_list_one, hidden_representation_list_two):
    list_corr_matrices = []

    for layer_id in range(len(hidden_representation_list_one) - 1):

        batch_size = hidden_representation_list_one[layer_id].shape[0]
        size_activation_map = hidden_representation_list_one[layer_id].shape[1]
        num_filters = hidden_representation_list_one[layer_id].shape[-1]

        # draw a random value from each of the CNN filters
        i_dim = np.random.choice(range(0, size_activation_map), batch_size)
        j_dim = np.random.choice(range(0, size_activation_map), batch_size)

        layer_one = []
        layer_two = []
        for index in range(batch_size):
            layer_one.append(hidden_representation_list_one[layer_id][index][i_dim[index], j_dim[index], :])
            layer_two.append(hidden_representation_list_two[layer_id][index][i_dim[index], j_dim[index], :])

        layer_one = np.array(layer_one)
        layer_two = np.array(layer_two)

        cross_corr_matrix = np.corrcoef(layer_one, layer_two, rowvar=False)[num_filters:, :num_filters]

        cross_corr_matrix[np.isnan(cross_corr_matrix)] = 0
        list_corr_matrices.append(cross_corr_matrix)

    return list_corr_matrices


# cross correlation function for both bipartite matching (hungarian method)
def bipartite_matching(corr_matrix_nn, crossover="unsafe_crossover"):
    corr_matrix_nn_tmp = copy.deepcopy(corr_matrix_nn)
    if crossover == "unsafe_crossover":
        list_neurons_x, list_neurons_y = linear_sum_assignment(corr_matrix_nn_tmp)
    elif crossover == "safe_crossover":
        corr_matrix_nn_tmp *= -1  # default of linear_sum_assignement is to minimize cost, we want to max "cost"
        list_neurons_x, list_neurons_y = linear_sum_assignment(corr_matrix_nn_tmp)
    elif crossover == "orthogonal_crossover":
        corr_matrix_nn_tmp = np.abs(corr_matrix_nn_tmp)
        list_neurons_x, list_neurons_y = linear_sum_assignment(corr_matrix_nn_tmp)
    elif crossover == "normed_crossover":
        corr_matrix_nn_tmp = np.abs(corr_matrix_nn_tmp)
        corr_matrix_nn_tmp *= -1
        list_neurons_x, list_neurons_y = linear_sum_assignment(corr_matrix_nn_tmp)
    elif crossover == "naive_crossover":
        list_neurons_x, list_neurons_y = list(range(corr_matrix_nn.shape[0])), list(range(corr_matrix_nn.shape[0]))
    else:
        raise ValueError('the crossover method is not defined')

    return list_neurons_x, list_neurons_y


# Algorithm 2
def permute_cnn(weights_list_copy, list_permutation):
    depth = 0

    for layer in range(len(list_permutation)):
        for index in range(7):
            if index == 0:
                # order filters
                weights_list_copy[index + depth] = weights_list_copy[index + depth][:, :, :, list_permutation[layer]]
            elif index in [1, 2, 3, 4, 5]:
                # order the biases and the batch norm parameters
                weights_list_copy[index + depth] = weights_list_copy[index + depth][list_permutation[layer]]
            elif index == 6:
                if (index + depth) != (len(weights_list_copy) - 1):
                    # order channels
                    weights_list_copy[index + depth] = weights_list_copy[index + depth][:, :, list_permutation[layer],
                                                       :]
                else:  # this is for the flattened fully connected layer

                    num_filters = len(list_permutation[layer])
                    weights_tmp = copy.deepcopy(weights_list_copy[index + depth])
                    activation_map_size = int(weights_tmp.shape[0] / num_filters)

                    for i in range(num_filters):
                        filter_id = list_permutation[layer][i]
                        weights_list_copy[index + depth][[num_filters * j + i for j in range(activation_map_size)]] = \
                            weights_tmp[[num_filters * j + filter_id for j in range(activation_map_size)]]

        depth = (layer + 1) * 6

    return weights_list_copy


def transplant_neurons(fittest_weights, weakest_weights, indices_transplant, indices_remove, layer, depth):

    for index in range(7):
        if index == 0:
            # order filters
            fittest_weights[index + depth][:, :, :, indices_remove[layer]] = weakest_weights[index + depth][:, :, :,
                                                                             indices_transplant[layer]]
        elif index == [1, 2, 3, 4, 5]:
            # order the biases and the batch norm parameters
            fittest_weights[index + depth][indices_remove[layer]] = weakest_weights[index + depth][
                indices_transplant[layer]]
        elif index == 6:
            if (index + depth) != (len(fittest_weights) - 1):
                # order channels
                fittest_weights[index + depth][:, :, indices_remove[layer], :] = weakest_weights[index + depth][:, :,
                                                                                 indices_transplant[layer], :]
            else:  # this is for the flattened fully connected layer

                num_filters = 32
                weights_tmp = copy.deepcopy(weakest_weights[index + depth])
                activation_map_size = int(weights_tmp.shape[0] / num_filters)

                for i in range(len(indices_transplant[layer])):
                    filter_id_transplant = indices_transplant[layer][i]
                    filter_id_remove = indices_remove[layer][i]
                    fittest_weights[index + depth][
                        [num_filters * j + filter_id_remove for j in range(activation_map_size)]] = weights_tmp[
                        [num_filters * j + filter_id_transplant for j in range(activation_map_size)]]

    return fittest_weights


def crossover_method(weights_one, weights_two, list_corr_matrices, crossover):

    list_ordered_indices_one = []
    list_ordered_indices_two = []

    if crossover == "naive":
        list_ordered_w_one = list(weights_one)
        list_ordered_w_two = list(weights_two)

    else:
        for index in range(len(list_corr_matrices)):
            corr_matrix_nn = list_corr_matrices[index]

            indices_one, indices_two = bipartite_matching(corr_matrix_nn, crossover)
            list_ordered_indices_one.append(indices_one)
            list_ordered_indices_two.append(indices_two)

        weights_nn_one_copy = list(weights_one)
        weights_nn_two_copy = list(weights_two)
        list_ordered_w_one = permute_cnn(weights_nn_one_copy, list_ordered_indices_one)
        list_ordered_w_two = permute_cnn(weights_nn_two_copy, list_ordered_indices_two)

    return list_ordered_indices_one, list_ordered_indices_two, list_ordered_w_one, list_ordered_w_two


def compute_q_values(list_cross_corr_copy):

    q_value_list = []
    for index in range(len(list_cross_corr_copy)):
        corr = list_cross_corr_copy[index]

        print(np.diag(corr))
        similarity = np.mean(np.abs(np.diag(corr)))
        q_value = -0.5*similarity+0.5
        #q_value = 0.5*similarity
        q_value_list.append(q_value)

    return q_value_list


def reset_weights_layer(weights, layer):

    # reset convolutional layers and batch norm parameters
    count = 0
    for index in range(layer*6, len(weights)-1):
        
        if count == 0:
            fan_in = np.prod(weights[index].shape)
            # He Normal
            reinit_weights = np.random.normal(loc=0.0, scale=np.sqrt(2/fan_in), size=weights[index].shape)
        
        elif count in [1]:
            reinit_weights = np.zeros(weights[index].shape)
            
        elif count in [2, 3, 4, 5]:
            reinit_weights = weights[index]
            
        weights[index] = reinit_weights
            
        count += 1
        
        if index % 5 == 0:
            count = 0

    # reset dense layers
    fan_in = np.prod(weights[-1].shape)
    weights[-1] = np.random.normal(loc=0.0, scale=np.sqrt(2/fan_in), size=weights[-1].shape)

    return weights


def mean_ensemble(model_one, model_two, x_test, y_test):

    def keras_function_layer(model, model_layer, data):
        hidden_func = keras.backend.function(model.layers[0].input, model_layer.output)
        result = hidden_func([data])

        return result

    logits_model_one = keras_function_layer(model_one, model_one.layers[-2], x_test)
    logits_model_two = keras_function_layer(model_two, model_two.layers[-2], x_test)

    ensemble_predictions = (logits_model_one + logits_model_two)/2
    ensemble_predictions = softmax(ensemble_predictions)
    class_prediction = np.argmax(ensemble_predictions, axis=1)

    loss = log_loss(y_test, ensemble_predictions)
    accuracy = accuracy_score(y_test, class_prediction)

    return loss


def get_fittest_parent(model_one, model_two, model_one_performance, model_two_performance, switch):

    # make sure that model_one is the fittest model
    if np.min(model_one_performance) > np.min(model_two_performance):
        model_one, model_two = model_two, model_one
        model_one_performance, model_two_performance = model_two_performance, model_one_performance
        switch = True

    return model_one, model_two, model_one_performance, model_two_performance, switch
