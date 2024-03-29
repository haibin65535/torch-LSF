import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np


    
class GMLLoss(nn.Module):
    def __init__(self,cls_num_list, beta = 1, gamma = 1, temperature=0.07, num_classes=100):
        super().__init__()
        T_base = 0.05
        self.register_parameter(
            'log_T_c__no_wd__',
            nn.Parameter(torch.full([1], temperature).log()),
        )
        # self.register_parameter(
        #     'log_T_s__no_wd__',
        #     nn.Parameter(torch.full([1], T_base).log()),
        # )
        self.register_buffer(
            'log_T_s__no_wd__',
            torch.full([1], T_base).log(),
        )
        self.beta = beta
        self.gamma = gamma
        self.num_classes = num_classes
        
        self.criterion = nn.CrossEntropyLoss()
        cls_num_list = torch.Tensor(cls_num_list).view(self.num_classes)
        self.cls_weight = torch.log_softmax(cls_num_list / cls_num_list.sum(),dim=0).cuda() 
        
    @property
    def T_c(self):
        return self.log_T_c__no_wd__.exp()
    
    @property
    def T_s(self):
        return self.log_T_s__no_wd__.exp()


    def get_logS_x_y(self, logits, weights, target):

        max_logit = logits.amax(1, keepdim=True).detach()
        logits = logits - max_logit
        
        one_hot = F.one_hot(target, self.num_classes).float()
        sumexp_logits_per_cls = (logits.exp() * weights) @ one_hot
        sum_weights_per_cls = weights @ one_hot
        meanexp_logits_per_cls = sumexp_logits_per_cls / sum_weights_per_cls
        
        logmeanexp_logits_per_cls = meanexp_logits_per_cls.log() + max_logit
        
        return logmeanexp_logits_per_cls
        
    def forward(self, query, q_labels, q_idx, key, k_labels, k_idx, sup_logits):
        q_dot_k = query @ key.T / self.T_c.detach()
        
        qk_mask = torch.ones_like(q_idx[:, None] != k_idx[None, :]).float()
        logS_x_y = self.get_logS_x_y(q_dot_k, qk_mask, k_labels)
        
        q_dot_k_T = (query @ key.T).detach() / self.T_c
        qk_mask_T = (q_idx[:, None] != k_idx[None, :]).float()
        logS_x_y_T = self.get_logS_x_y(q_dot_k_T, qk_mask_T, k_labels)
        
        loss_sup = F.cross_entropy(sup_logits / self.T_s
                               + self.cls_weight, q_labels)
        loss_con = self.criterion(logS_x_y
                               + self.cls_weight, q_labels)
        loss_con_T = self.criterion(logS_x_y_T
                               + self.cls_weight, q_labels)
        
        
        loss = self.gamma * loss_sup
        if self.beta > 0:
            loss += self.beta * (loss_con + loss_con_T)
        
        return loss