import ipdb
import os
from glob import glob
import pandas as pd
import numpy as np
import cv2
from model_as import *
from util_as_full import *

n_epochs = 50
learning_rate_val = 0.0003
weight_decay_rate =  0.00001
momentum = 0.9
batch_size = 64
lambda_recon = 0.9
lambda_adv = 0.1

# size of overlap of output patch
overlap_size = 7
# size of output patch
hiding_size = 256
# size of border
border_size = 40

trainset_path = '../data/places_trainset.pickle'
testset_path  = '../data/places_testset.pickle'
dataset_path = '/home/as5414/places/data_256'
model_path = '../models/run3_full_noovrlap/'
result_path= '../results/run3_full_noovrlap/'
pretrained_model_path = None#'../models/places/model-0'

if not os.path.exists(model_path):
    os.makedirs( model_path )

if not os.path.exists(result_path):
    os.makedirs( result_path )

if not os.path.exists( trainset_path ) or not os.path.exists( testset_path ):
    imagenet_images = []
    for dir, _, _, in os.walk(dataset_path):
        imagenet_images.extend( glob( os.path.join(dir, '*.jpg')))

    imagenet_images = np.hstack(imagenet_images)

    trainset = pd.DataFrame({'image_path':imagenet_images[:int(len(imagenet_images)*0.9)]})
    testset = pd.DataFrame({'image_path':imagenet_images[int(len(imagenet_images)*0.9):]})

    trainset.to_pickle( trainset_path )
    testset.to_pickle( testset_path )
# read dataset
else:
    trainset = pd.read_pickle( trainset_path )
    testset = pd.read_pickle( testset_path )

testset.index = range(len(testset))
testset = testset.ix[np.random.permutation(len(testset))]
is_train = tf.placeholder( tf.bool )

# learning rate placeholder
learning_rate = tf.placeholder( tf.float32, [])
# input image placeholder
images_tf = tf.placeholder( tf.float32, [batch_size, 256, 256, 3], name="images")

# labels for discriminator (1st batch positive samples and 2nd batch -ve)
labels_D = tf.concat( [tf.ones([batch_size]), tf.zeros([batch_size])], 0)
# labels for generator
labels_G = tf.ones([batch_size])
# output patch placeholder
images_hiding = tf.placeholder( tf.float32, [batch_size, hiding_size, hiding_size, 3], name='images_hiding')
#print(images_hiding.shape,images_tf.shape)
# load model
model = Model()

# main network
bn1, bn2, bn3, bn4, bn5, bn6, debn6, debn5, debn4, debn3, debn2, reconstruction_ori, reconstruction = model.build_reconstruction(images_tf, is_train)
#print(debn1.shape,debn2.shape,debn3.shape,debn4.shape,debn5.shape,debn6.shape,reconstruction_ori.shape)
#print('##########')
# discriminator for actual images
adversarial_pos = model.build_adversarial(images_hiding, is_train)
# discriminator for generated images
adversarial_neg = model.build_adversarial(reconstruction, is_train, reuse=True)
adversarial_all = tf.concat([adversarial_pos, adversarial_neg],0)

# compute masks for recon and overlap regions
# mask_recon = tf.pad(tf.ones([hiding_size - 2*border_size, hiding_size - 2*border_size]), [[border_size,border_size], [border_size,border_size]])
# mask_recon = tf.reshape(mask_recon, [hiding_size, hiding_size, 1])
# mask_recon = tf.concat([mask_recon]*3, 2)
# mask_overlap = mask_recon * (1-tf.concat([tf.reshape(tf.pad(tf.ones([hiding_size - 2*(border_size+overlap_size), hiding_size - 2*(border_size+overlap_size)]), [[(border_size+overlap_size),(border_size+overlap_size)], [(border_size+overlap_size),(border_size+overlap_size)]]), [hiding_size, hiding_size, 1])]*3,2))
# mask_recon = 1 - mask_recon
#print(mask_recon.shape,mask_overlap.shape)
# compute reconstruction loss (including overlapping region)
loss_recon_ori = tf.square( images_hiding - reconstruction )
loss_recon = tf.reduce_mean(tf.sqrt( 1e-5 + tf.reduce_sum(loss_recon_ori, [1,2,3]))) / 10.  # Loss for non-overlapping region
# loss_recon_overlap = tf.reduce_mean(tf.sqrt( 1e-5 + tf.reduce_sum(loss_recon_ori * mask_overlap, [1,2,3]))) # Loss for overlapping region
# loss_recon = loss_recon_center + loss_recon_overlap

# compute adverserial losses
loss_adv_D = tf.reduce_mean( tf.nn.sigmoid_cross_entropy_with_logits(logits=adversarial_all, labels=labels_D))
loss_adv_G = tf.reduce_mean( tf.nn.sigmoid_cross_entropy_with_logits(logits=adversarial_neg, labels=labels_G))

loss_G = loss_adv_G * lambda_adv + loss_recon * lambda_recon
loss_D = loss_adv_D * lambda_adv

# filter out weight variables and apply weight decay
var_G = filter( lambda x: x.name.startswith('GEN'), tf.trainable_variables())
var_D = filter( lambda x: x.name.startswith('DIS'), tf.trainable_variables())

W_G = filter(lambda x: x.name.endswith('W:0'), var_G)
W_D = filter(lambda x: x.name.endswith('W:0'), var_D)

loss_G += weight_decay_rate * tf.reduce_mean(tf.stack( map(lambda x: tf.nn.l2_loss(x), W_G)))
loss_D += weight_decay_rate * tf.reduce_mean(tf.stack( map(lambda x: tf.nn.l2_loss(x), W_D)))

sess = tf.InteractiveSession()

# compute gradients for G and D
optimizer_G = tf.train.AdamOptimizer( learning_rate=learning_rate )
grads_vars_G = optimizer_G.compute_gradients( loss_G, var_list=var_G )
grads_vars_G = map(lambda gv: gv if gv[0] is None else [tf.clip_by_value(gv[0], -10., 10.), gv[1]], grads_vars_G)
train_op_G = optimizer_G.apply_gradients( grads_vars_G )

optimizer_D = tf.train.AdamOptimizer( learning_rate=learning_rate )
grads_vars_D = optimizer_D.compute_gradients( loss_D, var_list=var_D )
grads_vars_D = map(lambda gv: gv if gv[0] is None else [tf.clip_by_value(gv[0], -10., 10.), gv[1]], grads_vars_D)
train_op_D = optimizer_D.apply_gradients( grads_vars_D )

saver = tf.train.Saver(max_to_keep=100)

tf.initialize_all_variables().run()

if pretrained_model_path is not None and os.path.exists( pretrained_model_path ):
    saver.restore( sess, pretrained_model_path )
    iters = 774*int(pretrained_model_path[-1]) - 1
else:
    iters = 0

loss_D_val = 0.
loss_G_val = 0.

for epoch in range(n_epochs):
    trainset.index = range(len(trainset))
    trainset = trainset.ix[np.random.permutation(len(trainset))]

    for start,end in zip(
            range(0, len(trainset), batch_size),
            range(batch_size, len(trainset), batch_size)):

        ### CHANGE here #####
        image_paths = trainset[start:end]['image_path'].values
        images_ori = map(lambda x: load_image( x ), image_paths)
        is_none = np.sum(map(lambda x: x is None, images_ori))
        if is_none > 0: continue

        # get cropped images
        images_crops = map(lambda x: crop_random(x), images_ori)
        images, crops,_,_ = zip(*images_crops)

        # Printing activations every 100 iterations
        if iters % 100 == 0:
            # do validation
            #### CHANGE here ####
            test_image_paths = testset[:batch_size]['image_path'].values
            test_images_ori = map(lambda x: load_image(x), test_image_paths)

            test_images_crop = map(lambda x: crop_random(x, x=32, y=32), test_images_ori)
            test_images, test_crops, xs,ys = zip(*test_images_crop)

            reconstruction_vals, recon_ori_vals, bn1_val,bn2_val,bn3_val,bn4_val,bn5_val,bn6_val,debn6_val,debn5_val,debn4_val, debn3_val, debn2_val, loss_G_val, loss_D_val = sess.run(
                    [reconstruction, reconstruction_ori, bn1,bn2,bn3,bn4,bn5,bn6,debn6,debn5,debn4, debn3, debn2, loss_G, loss_D],
                    feed_dict={
                        images_tf: test_images,
                        images_hiding: test_crops,
                        is_train: False
                        })

            # Generate result images every 500 iterations
            #### CHANGE here ####
            if iters % 500 == 0:
                ii = 0
                for rec_val, img,x,y in zip(reconstruction_vals, test_images, xs, ys):
                    rec_hid = (255. * (rec_val+1)/2.).astype(int)
                    rec_con = (255. * (img+1)/2.).astype(int)

                    #rec_hid[border_size : hiding_size - border_size, border_size : hiding_size - border_size] = rec_con[border_size : hiding_size - border_size, border_size : hiding_size - border_size]
                    cv2.imwrite( os.path.join(result_path, 'img_'+str(ii)+'.'+str(int(iters/100))+'.jpg'), rec_hid)
                    ii += 1
                    if ii > 50: break

                if iters == 0:
                    ii = 0
                    for test_image in test_images_ori:
                        test_image = (255. * (test_image+1)/2.).astype(int)
                        #test_image1 = np.zeros_like(test_image)
                        #test_image1[border_size : hiding_size - border_size, border_size : hiding_size - border_size] = test_image[border_size : hiding_size - border_size, border_size : hiding_size - border_size]
                        cv2.imwrite( os.path.join(result_path, 'img_'+str(ii)+'.ori.jpg'), test_image)
                        ii += 1
                        if ii > 50: break

            print "========================================================================"
            print bn1_val.max(), bn1_val.min()
            print bn2_val.max(), bn2_val.min()
            print bn3_val.max(), bn3_val.min()
            print bn4_val.max(), bn4_val.min()
            print bn5_val.max(), bn5_val.min()
            print bn6_val.max(), bn6_val.min()
            print debn6_val.max(), debn6_val.min()
            print debn5_val.max(), debn5_val.min()
            print debn4_val.max(), debn4_val.min()
            print debn3_val.max(), debn3_val.min()
            print debn2_val.max(), debn2_val.min()
            print recon_ori_vals.max(), recon_ori_vals.min()
            print reconstruction_vals.max(), reconstruction_vals.min()
            print loss_G_val, loss_D_val
            print "========================================================================="

            if np.isnan(reconstruction_vals.min() ) or np.isnan(reconstruction_vals.max()):
                print "NaN detected!!"
                ipdb.set_trace()

        # Generative Part is updated every iteration
        _, loss_G_val, adv_pos_val, adv_neg_val, loss_recon_val, loss_adv_G_val, reconstruction_vals, recon_ori_vals, bn1_val,bn2_val,bn3_val,bn4_val,bn5_val,bn6_val,debn6_val,debn5_val,debn4_val, debn3_val, debn2_val= sess.run(
                [train_op_G, loss_G, adversarial_pos, adversarial_neg, loss_recon, loss_adv_G, reconstruction, reconstruction_ori, bn1,bn2,bn3,bn4,bn5,bn6,debn6,debn5,debn4, debn3, debn2],
                feed_dict={
                    images_tf: images,
                    images_hiding: crops,
                    learning_rate: learning_rate_val,
                    is_train: True
                    })

        _, loss_D_val, adv_pos_val, adv_neg_val = sess.run(
                [train_op_D, loss_D, adversarial_pos, adversarial_neg],
                feed_dict={
                    images_tf: images,
                    images_hiding: crops,
                    learning_rate: learning_rate_val/10.,
                    is_train: True
                        })

        print "Iter:", iters, "Gen Loss:", loss_G_val, "Recon Loss:", loss_recon_val, "Gen ADV Loss:", loss_adv_G_val,  "Dis Loss:", loss_D_val, "||||", adv_pos_val.mean(), adv_neg_val.min(), adv_neg_val.max()

        iters += 1


    saver.save(sess, model_path + 'model', global_step=epoch)#+int(pretrained_model_path[-1]))
    learning_rate_val *= 0.99



