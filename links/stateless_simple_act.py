# -*- coding: utf-8 -*-
"""
Created on Wed May 10 19:42:51 2017

@author: sakurai
"""

import numpy as np
import chainer
import chainer.functions as F
import chainer.functions as L
import six


class StatelessSimpleACT(chainer.Chain):
    def __init__(self, in_size, s_size, out_size,
                 epsilon=0.01, max_ponder_steps=100):
        super(StatelessSimpleACT, self).__init__(
            l_xs=L.Linear(in_size + 1, s_size),
            l_ss=L.Linear(s_size, s_size),
            l_sh=L.Linear(s_size, 1),
            l_sy=L.Linear(s_size, out_size))
        self.in_size = in_size
        self.s_size = s_size
        self.out_size = out_size
        self.epsilon = epsilon
        self.max_ponder_steps = max_ponder_steps

    def __call__(self, x_t, s_t):
        xp = self.xp
        batch_size = x_t.shape[0]

        ponder_costs = []
        s_t_n = s_t

        s_t_ns = []
        y_t_ns = []
        p_t_ns = []
        r_t_n = chainer.Variable(xp.ones((batch_size, 1), np.float32))
        r_t = [r_t_n]
        n_t = xp.full((batch_size, 1), -1, np.int32)
        already_halted = xp.full((batch_size, 1), False, np.bool)

        n = 0
        x_t_n = F.hstack((x_t, xp.ones((batch_size, 1), x_t.dtype)))
        x_t_n = self.l_xs(x_t_n)

        for n in six.moves.range(self.max_ponder_steps):
            if xp.all(already_halted):
                break

            s_t_n = F.tanh(x_t_n + self.l_ss(s_t_n))
            y_t_n = self.l_sy(s_t_n)
            h_t_n = F.sigmoid(self.l_sh(s_t_n))

            if n < self.max_ponder_steps - 1:  # normal case
                halt = r_t_n.data - h_t_n.data < self.epsilon
            else:  # truncation by max ponder steps
                halt = np.full((batch_size, 1), True)
            p_t_n = F.where(already_halted,
                            xp.zeros((batch_size, 1), xp.float32),
                            F.where(halt,
                                    r_t_n,
                                    h_t_n))

            s_t_ns.append(s_t_n)
            y_t_ns.append(y_t_n)
            p_t_ns.append(p_t_n)
            r_t_n -= p_t_n
            r_t.append(r_t_n)

            now_halted = xp.logical_and(r_t_n.data < self.epsilon,
                                        xp.logical_not(already_halted))
            n_t[now_halted] = n
            already_halted = xp.logical_or(already_halted, now_halted)

            # compute x_t_n for n > 1 once
            if n == 0:
                x_t_n = F.hstack(
                    (x_t, xp.zeros((batch_size, 1), x_t.dtype)))
                x_t_n = self.l_xs(x_t_n)
        print(n + 1, end=', ')

        s_t_ns = F.stack(s_t_ns, 1)
        y_t_ns = F.stack(y_t_ns, 1)
        p_t_ns = F.stack(p_t_ns, 1)
        s_t = F.batch_matmul(p_t_ns, s_t_ns, transa=True)
        y_t = F.batch_matmul(p_t_ns, y_t_ns, transa=True)

        s_t = s_t.reshape(batch_size, -1)
        y_t = y_t.reshape(batch_size, -1)
        remainders_at_halt = F.concat(r_t)[np.arange(batch_size), n_t.ravel()]
        ponder_costs = n_t.ravel().astype(xp.float32) + remainders_at_halt
        ponder_cost = F.sum(ponder_costs)

        return y_t, s_t, ponder_cost
