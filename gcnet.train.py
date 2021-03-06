print 'Loading dependencies...'

import math, sys, time
import numpy as np

from keras import backend as K
from keras.applications import vgg16 as vgg16
from keras.layers import Dense, Dropout, Input, Flatten, LSTM, TimeDistributed, RepeatVector, Embedding, merge, Bidirectional, Lambda
from keras.models import Model

Bi = Bidirectional
_LSTM = LSTM
LSTM = lambda s, rs=True, gb=False, ur=True: _LSTM(s, return_sequences=rs, consume_less='gpu', unroll=ur, go_backwards=gb)
BLSTM = lambda s, rs=True, gb=False, ur=True: Bi(LSTM(s, rs, gb, ur))
Sum = Lambda(lambda x: K.sum(x, axis=1), output_shape=lambda s: (s[0], s[2]))

vocabSize = 6001
wordVectorSize = 300
captionLength = 16
gifFrames = 16

print 'Building GCNet...'
gifFramesVGG16 = Input(shape=(gifFrames, 1000))

# Trained Word Embeddings
embeddingMatrix = np.load('./embeddingMatrix.' + str(vocabSize - 1) + '.npy')
WordEmbedding = Embedding(input_dim=vocabSize, 
    output_dim=wordVectorSize, 
    mask_zero=True, 
    input_length=captionLength - 1, 
    weights=[embeddingMatrix], 
    trainable=False)

captionInput = Input(shape=(captionLength - 1,), dtype='int32')
wordVectorizedCaption = WordEmbedding(captionInput) 

dGIFFramesVGG16 = Dropout(.15)(gifFramesVGG16)
gifEncoder = BLSTM(1024)(dGIFFramesVGG16)
gifEncoder = Dropout(.15)(gifEncoder)
gifEncoder = LSTM(1024, rs=False)(gifEncoder)

gifFramesVGG16Sum = Sum(gifFramesVGG16)

encodedGIF = merge([gifEncoder, gifFramesVGG16Sum], mode='concat')

repeatedEncodedGIF = RepeatVector(captionLength - 1)(encodedGIF)

concatenatedWordVectorsAndEncodedGIF = merge([wordVectorizedCaption, repeatedEncodedGIF], mode='concat')

concatenatedWordVectorsAndEncodedGIF = Dropout(.15)(concatenatedWordVectorsAndEncodedGIF)
gifCaptionEncoder = BLSTM(1024)(concatenatedWordVectorsAndEncodedGIF)
gifCaptionEncoder = Dropout(.15)(gifCaptionEncoder)
gifCaptionEncoder = LSTM(1024, rs=False)(gifCaptionEncoder)

concatenatedEncoders = merge([gifCaptionEncoder, encodedGIF], mode='concat')

concatenatedEncoders = Dropout(.15)(concatenatedEncoders)
nextWord = Dense(vocabSize, activation='softmax')(concatenatedEncoders)

GCNet = Model([gifFramesVGG16, captionInput], nextWord)
GCNet.compile(loss='sparse_categorical_crossentropy', 
    optimizer='rmsprop', 
    metrics=['accuracy'])
GCNet.summary()

# At the very least, the last 625 GIFs, assuming 16 GIF frames.
numValidation = 10000
numEpochs = 100
batchSize = 256

print 'Loading caption data...'
dataYRaw = np.load('dataY.captions.' + str(captionLength) + '.npy')

expandedLen = len(dataYRaw) * captionLength
dataX = np.zeros((expandedLen, captionLength-1), dtype='int32')
dataY = np.zeros((expandedLen, 2), dtype='int32')

print 'Expanding caption data...'
iExpanded = 0
for iCaption in range(len(dataYRaw)):

    caption = dataYRaw[iCaption][1:]

    for iWord in range(captionLength):

        dataX[iExpanded][:iWord] = caption[:iWord]
        dataY[iExpanded] = [dataYRaw[iCaption][0], caption[iWord]]

        iExpanded += 1
        if np.sum(caption[iWord:]) <= 0:
            break

print 'Expanded dataset: ' + str(iExpanded) + ' / ' + str(expandedLen)

dataX = dataX[:iExpanded]
dataY = dataY[:iExpanded]

dataX, dataXVal = np.split(dataX, [-numValidation])
dataY, dataYVal = np.split(dataY, [-numValidation])

dataYIDs, dataYWords = np.split(dataY, [1], 1)
dataYValIDs, dataYValWords = np.split(dataYVal, [1], 1)

dataYIDs = dataYIDs.flatten()
dataYValIDs = dataYValIDs.flatten()

dataYWords = dataYWords.reshape((len(dataYWords), 1))
dataYValWords = dataYValWords.reshape((len(dataYValWords), 1))

print 'Loading precomputed VGG16 frames...'
precomputedVGG16Frames = np.load('./precomputedVGG16Frames.' + str(gifFrames) + '.npy')

numBatches = len(dataYWords) / batchSize + 1
numValBatches = numValidation / batchSize + 1

print 'Start training...'
for epoch in range(numEpochs):

    shuffleIndices = np.random.choice(np.arange(len(dataX)), len(dataX), False)
    dataX = dataX[shuffleIndices]
    dataYIDs = dataYIDs[shuffleIndices]
    dataYWords = dataYWords[shuffleIndices]

    print '\nEpoch ' + str(epoch)

    # Train
    i = 0
    lastStartIndex = 0
    tLoss = 0.0
    tAcc = 0.0
    tTime = 0.0
    while True:

        tStart = time.time()

        batchIDs = dataYIDs[lastStartIndex:lastStartIndex+batchSize]
        batchCaptions = dataX[lastStartIndex:lastStartIndex+batchSize]
        batchWords = dataYWords[lastStartIndex:lastStartIndex+batchSize]
        lastStartIndex += batchSize

        if len(batchIDs) <= 0:
            break

        batchImages = precomputedVGG16Frames[batchIDs]

        result = GCNet.train_on_batch([batchImages, batchCaptions], batchWords)

        tDelta = time.time() - tStart
        if i == 1:
            tTime += 2 * tDelta
        elif i > 0:
            tTime += tDelta

        progress = int(math.floor(30.0 * (i+1) / numBatches))
        progressBar = '\rTrain:\t\t' + str((i+1)*batchSize) + '/' + str(numBatches*batchSize) + ' [' + ('=' * progress) + ('>' if 0 < progress < 30 else '') + ('.' * (30 - progress)) + '] - ETA: %ds - loss: %f - acc: %f'%(int((numBatches-i)*tTime/(i+1)), tLoss/(i+1), tAcc/(i+1)) + '\t\t'  

        sys.stdout.write(progressBar)
        sys.stdout.flush()

        tLoss += result[0]
        tAcc += result[1]
        i += 1

    print ''

    # Validation
    i = 0
    lastStartIndex = 0
    tLoss = 0.0
    tAcc = 0.0
    while True:

        batchIDs = dataYValIDs[lastStartIndex:lastStartIndex+batchSize]
        batchCaptions = dataXVal[lastStartIndex:lastStartIndex+batchSize]
        batchWords = dataYValWords[lastStartIndex:lastStartIndex+batchSize]
        lastStartIndex += batchSize

        if len(batchIDs) <= 0:
            break

        batchImages = precomputedVGG16Frames[batchIDs]

        result = GCNet.test_on_batch([batchImages, batchCaptions], batchWords)

        progress = int(math.floor(30.0 * (i+1) / numValBatches))
        progressBar = '\rValidation:\t' + str((i+1)*batchSize) + '/' + str(numValBatches*batchSize) + '\t[' + ('=' * progress) + ('>' if 0 < progress < 30 else '') + ('.' * (30 - progress)) + '] - loss: %f - acc: %f'%(tLoss/(i+1), tAcc/(i+1)) + '\t\t'  

        sys.stdout.write(progressBar)
        sys.stdout.flush()

        tLoss += result[0]
        tAcc += result[1]
        i += 1

    GCNet.save_weights('gcnet.weights.acc' + str(round(tAcc/i * 100, 4)) + '_loss' + str(round(tLoss/i, 4)) + '_epoch' + str(epoch) + '.h5', True)