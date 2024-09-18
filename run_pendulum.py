#Copyright (C) 2021. Huawei Technologies Co., Ltd. All rights reserved.
#This program is free software; 
#you can redistribute it and/or modify
#it under the terms of the MIT License.
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the MIT License for more details.

import torch
from codebase import utils as ut
import argparse
from pprint import pprint
cuda = torch.cuda.is_available()
import torch
import torch.nn as nn
import torch.optim as optim
from torch import autograd
from torch.autograd import Variable
import numpy as np
import math
import time
from torch.utils import data
from utils import get_batch_unin_dataset_withlabel, _h_A
import matplotlib.pyplot as plt
import random
import torch.utils.data as Data
from PIL import Image
import os
import numpy as np
from torchvision import transforms
from codebase import utils as ut
from codebase.models.mask_vae_pendulum import CausalVAE
import argparse
from pprint import pprint
cuda = torch.cuda.is_available()
from torchvision.utils import save_image

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

parser.add_argument('--epoch_max',   type=int, default=101,    help="Number of training epochs")
parser.add_argument('--iter_save',   type=int, default=50, help="Save model every n epochs")
parser.add_argument('--toy',       type=str, default="pendulum_mask",     help="The toy dataset")
parser.add_argument('--initial',       type=bool, default=True,     help="Initialize the dag matrix")
parser.add_argument('--seed',   type=int, default=42,    help="seed of training")

args = parser.parse_args()
device = torch.device("cuda:0" if(torch.cuda.is_available()) else "cpu")
torch.manual_seed(args.seed)

upload = False

if upload:
	import wandb
	wandb.init(project = 'CausalVAE')
	runconfig = dict(vars(args))
	wandb.config.update(runconfig, allow_val_change=True)
	wandb.save(os.path.abspath(__file__), policy = 'now')
	wandb.save('./codebase/*', policy = 'now')
	wandb.save('./codebase/models/*', policy = 'now')
	wandb.save('./codebase/models/nns/*', policy = 'now')


class DeterministicWarmup(object):
	"""
	Linear deterministic warm-up as described in
	[S?nderby 2016].
	"""
	def __init__(self, n=100, t_max=1):
		self.t = 0
		self.t_max = t_max
		self.inc = 1/n

	def __iter__(self):
		return self

	def __next__(self):
		t = self.t + self.inc

		self.t = self.t_max if t > self.t_max else t
		return self.t
layout = [
	('model={:s}',  'causalvae'),
	('toy={:s}', str(args.toy))
]
model_name = '_'.join([t.format(v) for (t, v) in layout])
pprint(vars(args))
print('Model name:', model_name)
lvae = CausalVAE(name=model_name, z_dim=16, initial=args.initial).to(device)
print(lvae)
# wandb.watch(lvae, log_freq = 100)
if not os.path.exists('./figs_vae_p/'): 
	os.makedirs('./figs_vae_p/')

dataset_dir = './causal_data/pendulum'
train_dataset = get_batch_unin_dataset_withlabel(dataset_dir, 64)
test_dataset = get_batch_unin_dataset_withlabel(dataset_dir, 1)
optimizer = torch.optim.Adam(lvae.parameters(), lr=1e-3, betas=(0.9, 0.999))
beta = DeterministicWarmup(n=100, t_max=1) # Linear warm-up from 0 to 1 over 50 epoch

def save_model_by_name(model, global_step):
	save_dir = os.path.join('checkpoints', model.name)
	if not os.path.exists(save_dir):
		os.makedirs(save_dir)
	file_path = os.path.join(save_dir, 'model-{:05d}.pt'.format(global_step))
	state = model.state_dict()
	torch.save(state, file_path)
	print('Saved to {}'.format(file_path))

step = 0

test_u, test_l = next(iter(test_dataset))
test_u, test_l = test_u.to(device), test_l.to(device)

import tqdm

bar = tqdm.tqdm(range(args.epoch_max * len(train_dataset)))

m = len(train_dataset)
save_image(test_u[0], 'figs_vae_p/reconstructed_image_true.png', value_range = (0,1))
for epoch in range(args.epoch_max):
	lvae.train()
	total_loss = 0
	total_rec = 0
	total_kl = 0
	for u, l in train_dataset:
		optimizer.zero_grad()
		u = u.to(device)
		L, kl, rec, reconstructed_image,_ = lvae.negative_elbo_bound(u,l,sample = False)
		
		dag_param = lvae.dag.A
		h_a = _h_A(dag_param, dag_param.size()[0])
		L = L + 3*h_a + 0.5*h_a*h_a - torch.norm(dag_param) 
		bar.update(1)
		step += 1
		L.backward()
		optimizer.step()

		total_loss += L.item()
		total_kl += kl.item() 
		total_rec += rec.item() 

	if epoch % 10 == 0:
		with torch.no_grad():
			L, kl, rec, reconstructed_image,_ = lvae.negative_elbo_bound(test_u,test_l,sample = False)
			save_image(reconstructed_image[0], 'figs_vae_p/reconstructed_image_{}.png'.format(epoch), value_range = (0,1))

		
	if epoch % 10 == 0:
		print(str(epoch)+' loss:'+str(total_loss/m)+' kl:'+str(total_kl/m)+' rec:'+str(total_rec/m)+'m:' + str(m))

	if upload:
		wandb.log({
			'loss': total_loss/m,
			'kl': total_kl/m,
			'rec': total_rec/m
		},
		step = step)
ut.save_model_by_name(lvae, epoch)


	# if epoch % args.iter_save == 0:
	# 	ut.save_model_by_name(lvae, epoch)

