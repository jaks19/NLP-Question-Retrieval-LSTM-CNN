from preprocess2 import *
from scoring_metrics import *
from cnn_utils2 import *

import torch
from torch.autograd import Variable

import time

saved_model_name = "best_cnn2"

'''Hyperparams dashboard'''
margin = 0.3
lr = 10**-3
truncation_val_title = 40
truncation_val_body = 60
dropout = 0.2


''' Data Prep '''
word2vec = get_words_and_embeddings()
id2Data = questionID_to_questionData_truncate(truncation_val_title, truncation_val_body)

training_data = training_id_to_similar_different()
trainingQuestionIds = list(training_data.keys())[:]

dev_data = devTest_id_to_similar_different(dev=True)
dev_question_ids = list(dev_data.keys())[:]

test_data = devTest_id_to_similar_different(dev=False)
test_question_ids = list(test_data.keys())


''' Model Specs '''
# CNN parameters
input_size = len(word2vec[list(word2vec.keys())[0]])
hidden_size = 667
kernel_size = 3
stride = 1
padding = 0
dilation = 1
groups = 1
bias = True

# CNN model
cnn = torch.nn.Sequential()
cnn.add_module('drop', torch.nn.Dropout(p = dropout))
cnn.add_module('conv', torch.nn.Conv1d(in_channels = input_size, out_channels = hidden_size, kernel_size = kernel_size, padding = padding, dilation = dilation, groups = groups, bias = bias))
cnn.add_module('tanh', torch.nn.Tanh())
cnn.add_module('norm', torch.nn.BatchNorm1d(num_features = hidden_size))

# Loss function
loss_function = torch.nn.MultiMarginLoss(margin=margin)

# Optimizer
optimizer = torch.optim.Adam(cnn.parameters(), lr=lr)


''' Procedural parameters '''
batch_size = 100
num_differing_questions = 20
num_epochs = 5
num_batches = round(len(trainingQuestionIds)/batch_size)


def train_model(cnn, optimizer, batch_ids, batch_data, word2vec, id2Data, truncation_val):
    cnn.train()
    optimizer.zero_grad()

    sequence_ids, dict_sequence_lengths = organize_ids_training(batch_ids, batch_data, num_differing_questions)

    candidates_qs_tuples_matrix = construct_qs_matrix_training(sequence_ids, cnn, word2vec, id2Data, dict_sequence_lengths, input_size, num_differing_questions, truncation_val, candidates=True)
    main_qs_tuples_matrix = construct_qs_matrix_training(batch_ids, cnn, word2vec, id2Data, dict_sequence_lengths, input_size, num_differing_questions, truncation_val, candidates=False)
    similarity_matrix = torch.nn.functional.cosine_similarity(candidates_qs_tuples_matrix, main_qs_tuples_matrix, dim=2, eps=1e-08)

    target = Variable(torch.LongTensor([0] * int(len(sequence_ids)/(1+num_differing_questions))))
    loss_batch = loss_function(similarity_matrix, target)

    loss_batch.backward()
    optimizer.step()

    print("loss_on_batch:", loss_batch.data[0], " time_on_batch:", time.time() - start)
    return


def eval_model(cnn, ids, data, word2vec, id2Data, truncation_val):
    cnn.eval()
    sequence_ids, p_pluses_indices_dict = organize_test_ids(ids, data)

    candidates_qs_tuples_matrix = construct_qs_matrix_testing(sequence_ids, cnn, word2vec, id2Data, input_size, num_differing_questions, truncation_val, candidates=True)
    main_qs_tuples_matrix = construct_qs_matrix_testing(ids, cnn, word2vec, id2Data, input_size, num_differing_questions, truncation_val, candidates=False)

    similarity_matrix = torch.nn.functional.cosine_similarity(candidates_qs_tuples_matrix, main_qs_tuples_matrix, dim=2, eps=1e-08)
    MRR_score = get_MRR_score(similarity_matrix, p_pluses_indices_dict)
    MAP_score = get_MAP_score(similarity_matrix, p_pluses_indices_dict)
    avg_prec_at_1 = avg_precision_at_k(similarity_matrix, p_pluses_indices_dict, 1)
    avg_prec_at_5 = avg_precision_at_k(similarity_matrix, p_pluses_indices_dict, 5) 
    return MRR_score, MAP_score, avg_prec_at_1, avg_prec_at_5


'''Begin training'''
for epoch in range(num_epochs):

    # Train on whole training data set
    for batch in range(1, num_batches+1):
        if batch == 121 or batch == 98: # memory error with this batch
            continue
        start = time.time()
        questions_this_training_batch = trainingQuestionIds[batch_size * (batch - 1):batch_size * batch]
        print("Working on batch #: ", batch)
        train_model(cnn, optimizer, questions_this_training_batch, training_data, word2vec, id2Data, truncation_val)
        
    # Evaluate on dev and test sets for MRR score
    test_scores = eval_model(cnn, test_question_ids, test_data, word2vec, id2Data, truncation_val) 
    print("MRR score on test set:", test_scores[0])
    dev_scores = eval_model(cnn, dev_question_ids, dev_data, word2vec, id2Data, truncation_val)
    print("MRR score on dev set:", dev_scores[0])
    print("MAP score on dev set:", dev_scores[1])
    print("MAP score on test set:", test_scores[1])
    print("Precision at 1 score on dev set:", dev_scores[2])
    print("Precision at 1 score on test set:", test_scores[2])
    print("Precision at 5 score on dev set:", dev_scores[3])
    print("Precision at 5 score on test set:", test_scores[3])

    # Log results to local logs.txt file
    with open('logs_cnn.txt', 'a') as log_file:
        log_file.write('epoch: ' + str(epoch) + '\n')
        log_file.write('lr: ' + str(lr) +  ' marg: ' + str(margin) + '\n' )        
        log_file.write('dev_MRR: ' +  str(dev_scores[0]) + '\n')
        log_file.write('test_MRR: ' +  str(test_scores[0]) + '\n')
        log_file.write('dev_MAP: ' +  str(dev_scores[1]) + '\n')
        log_file.write('test_MAP: ' +  str(test_scores[1]) + '\n')
        log_file.write('dev_p_at_1: ' +  str(dev_scores[2]) + '\n')
        log_file.write('test_p_at_1: ' +  str(test_scores[2]) + '\n')
        log_file.write('dev_p_at_5: ' +  str(dev_scores[3]) + '\n')
        log_file.write('test_p_at_5: ' +  str(test_scores[3]) + '\n')

    # Save model for this epoch
    torch.save(cnn, '../Pickle/' + saved_model_name + '_epoch' + str(epoch) + '.pt')