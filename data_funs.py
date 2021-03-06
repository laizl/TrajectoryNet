from __future__ import division
import tensorflow as tf
import sys
import csv

import numpy as np
import math
import sklearn.preprocessing
import os
import time
import pandas as pd
import util
from param import WIDTH
from param import FeatureName
import config
import param
from param import FENWEI_MAX
from param import FILTER_K


class Data:
    @staticmethod
    def splitDataset(mmsi, tr_mmsi, vl_tmmsi):
        test_index = Data.get_match_index(mmsi, tr_mmsi)
        val_index = Data.get_match_index(mmsi, vl_tmmsi)
        train_index = np.delete(np.array(range(len(mmsi))), np.concatenate([test_index, val_index]))
        return (train_index, test_index, val_index)

    @staticmethod
    def randomSplitDataset(mmsi, train_perc=0.5, val_perc=0.1):
        mmsi = np.array(mmsi)
        seq_len = mmsi.shape[0]
        test_perc = 1 - train_perc - val_perc
        rdn_perm = np.random.permutation(seq_len)
        train_index = rdn_perm[0:int(seq_len * train_perc)]
        test_index = rdn_perm[int(seq_len * train_perc): int(seq_len * (train_perc + test_perc))]
        val_index = rdn_perm[int(seq_len * (train_perc + test_perc)): seq_len]
        return (train_index, test_index, val_index)

    @staticmethod
    def get_match_index(mmsi, target):
        unique_mmsi = np.unique(mmsi)
        result = np.concatenate([np.where(mmsi == unique_mmsi[i]) for i in target], axis=1)[0]
        return result

    @staticmethod
    def upsample(data, cls, times):
        (X_train, y_train, stop_train) = data
        labels = [set(i) for i in y_train]
        samples = [cls in i for i in labels]
        sample_index = np.where(samples)[0]
        sample_x = np.repeat(X_train[:, sample_index, :], times - 1, axis=1)
        sample_y = np.repeat(y_train[sample_index, :], times - 1, axis=0)
        sample_stop = np.repeat(stop_train[sample_index], times - 1, axis=0)
        X_train = np.concatenate((X_train, sample_x), axis=1)
        y_train = np.vstack((y_train, sample_y))
        stop_train = np.hstack((stop_train, sample_stop))
        return (X_train, y_train, stop_train)

    # cut sequence into smaller sequences specified by the conf
    # 将序列切成指定长度的
    @staticmethod
    def reorganizeSeq(x, y, mmsi, exp_seq_len):
        num_features = x.shape[2]
        # 总共可以切出的序列个数
        num_total_seq = int(sum([math.ceil(i) for i in mmsi[1] / exp_seq_len]))
        new_data = np.zeros((num_total_seq, exp_seq_len, num_features))
        new_label = np.zeros((num_total_seq, exp_seq_len))
        # 0行存放编号 1行存放序列长度
        new_mmsi = np.zeros((2, num_total_seq)).astype(int)
        count = 0
        for v in range(len(mmsi[0])):  # iterate each vessel
            # 每个用户的数据
            # print v
            vessel_data = x[v]
            vessel_lab = y[v]
            # 用户编号
            vessel_mmsi = mmsi[0][v]
            # print(mmsi[0][v])
            # get full sequences first
            # 各个用户能切出的序列个数
            num_full_seq = mmsi[1][v] // exp_seq_len
            if num_full_seq:
                # full_seq的shape为当前用户的（总个数，序列长度，特征）
                full_seq = vessel_data[0:num_full_seq * exp_seq_len].reshape((num_full_seq, exp_seq_len, num_features))
                full_lab = vessel_lab[0:num_full_seq * exp_seq_len].reshape((num_full_seq, exp_seq_len))
                new_data[count:(count + num_full_seq)] = full_seq
                new_label[count:(count + num_full_seq)] = full_lab
                new_mmsi[0][count:(count + num_full_seq)] = vessel_mmsi
                new_mmsi[1][count:(count + num_full_seq)] = exp_seq_len
                count += num_full_seq

            # 序列切片多出来的长度保存起来
            remain_seq = np.zeros((exp_seq_len, num_features))
            remain_seq[0:(mmsi[1][v] - num_full_seq * exp_seq_len)] = vessel_data[num_full_seq * exp_seq_len:mmsi[1][v]]
            remain_lab = np.zeros(exp_seq_len)
            remain_lab[0:(mmsi[1][v] - num_full_seq * exp_seq_len)] = vessel_lab[num_full_seq * exp_seq_len:mmsi[1][v]]
            new_data[count] = remain_seq
            new_label[count] = remain_lab
            new_mmsi[0][count] = vessel_mmsi
            new_mmsi[1][count] = mmsi[1][v] - num_full_seq * exp_seq_len
            count += 1
        return (new_data, new_label, new_mmsi)

    #处理原始数据，提取经纬度，时间，与标签对应
    @staticmethod
    def sovle_row_data(interval):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"

        valiable_user_data = open("./data/have_label_user.txt","r")
        user_list = valiable_user_data.readlines()
        for i in user_list:
            user_id = i[0:3]
            label_txt_name = datadir + user_id+"/labels.txt"
            label_file = open(label_txt_name,"r")
            #label文件 数据还是字符串
            list_label = label_file.readlines()[1:]
            #label_list 数据是label数组
            label_list = []
            for i in list_label:
                l = i[0:len(i)-1].split("\t")
                label_list.append(l)

            plt_path = datadir + user_id + "/Trajectory"
            list_plt_name = os.listdir(plt_path)

            user_data = datadir + user_id + "/userdata_interval_"+str(interval)+".csv"
            user_data_file = open(user_data,"w")

            label_time_index = 0

            #循环处理所有plt文件
            i = 0
            while(i < len(list_plt_name)):

                is_finish = False
                plt_name = list_plt_name[i]
                print("处理", plt_name)

                plt_file_name = plt_path + "/" + plt_name
                #plt_time_str = plt_name[0:4] + "/" +plt_name[4:6] + "/" +plt_name[6:8] +" " + plt_name[8:10] +":"+plt_name[10:12]+":"+plt_name[12:14]
                #plt_time = time.strptime(plt_time_str,'%Y/%m/%d %H:%M:%S')
                #if plt_time
                plt_file = open(plt_file_name,"r")
                data = plt_file.readlines()
                data = data[6:len(data)]

                #plt文件的起始时间
                plt_start_time_str = data[0]
                plt_end_time_str = data[-1]
                plt_start_time_list = plt_start_time_str[0:len(plt_start_time_str)-1].split(",")
                plt_start_time = time.strptime(plt_start_time_list[-2] + " " + plt_start_time_list[-1],'%Y-%m-%d %H:%M:%S')
                plt_end_time_list = plt_end_time_str[0:len(plt_end_time_str)-1].split(",")
                plt_end_time = time.strptime(plt_end_time_list[-2] + " " + plt_end_time_list[-1],'%Y-%m-%d %H:%M:%S')

                #label 当前起始时间
                label_start_time = time.strptime(label_list[label_time_index][0], '%Y/%m/%d %H:%M:%S')
                label_end_time = time.strptime(label_list[label_time_index][1], '%Y/%m/%d %H:%M:%S')

                #如果plt_end_time < 当前label_start_time 处理下一个plt文件
                if plt_end_time <= label_start_time:
                    i+=1
                    continue
                elif plt_start_time >= label_end_time :
                    #重复此次循环
                    i-=1
                    label_time_index += 1
                    if label_time_index > len(label_list)-1:
                        is_finish = True
                else:
                    #处理plt文件中的内容
                    print("处理有标签的文件",plt_name)

                    last_time = None
                    k = 0
                    while(k < len(data)):
                        line = data[k]
                        line_time_list = line[0:len(line)-1].split(",")
                        line_time = time.strptime(line_time_list[-2] + " " + line_time_list[-1],'%Y-%m-%d %H:%M:%S')
                        #print(line_time,label_start_time,label_end_time)

                        if line_time >= label_start_time and line_time <= label_end_time:
                            if k == 0:
                                last_time = line_time
                            else:
                                if line_time == last_time:
                                    last_time = line_time
                                    k+=1
                                    continue
                            result_line = user_id +"," + line[0:len(line)-1] + "," + label_list[label_time_index][-1] + "," +str(label_time_index)
                            user_data_file.write(result_line + "\n")
                            last_time = line_time
                            k+=interval
                        elif line_time >label_end_time:

                            label_time_index += 1
                            if label_time_index > len(label_list)-1:
                                is_finish = True
                                break
                            label_start_time = time.strptime(label_list[label_time_index][0], '%Y/%m/%d %H:%M:%S')
                            label_end_time = time.strptime(label_list[label_time_index][1], '%Y/%m/%d %H:%M:%S')
                        elif line_time <label_start_time:
                            k+=1
                    #处理下一个文件
                #关闭当前plt文件
                if is_finish:
                    print("当前用户处理完毕",user_id)
                    plt_file.close()
                    break
                i+=1

            label_file.close()
            #plt_file.close()
            user_data_file.close()

    #计算特征
    @staticmethod
    def caculate_feature(interval_list):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        feature_num = 9
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        for interval in interval_list:
            print("处理%d"%(interval))
            for user in user_list:
                user_id = user[0:3]
                user_data_name = datadir + user_id + "/userdata_interval_"+str(interval)+".csv"
                #user_data_name = datadir + user_id + "/userdata.csv"
                print("开始处理",user_id)
                user_data_file = open(user_data_name,"r")

                # user_data_file = np.loadtxt(user_data_name,dtype=np.str,delimiter=",")
                # label_list = user_data_file[:,-1]
                # label_list = label_list.astype(int)
                # label_unique,label_index,label_count = np.unique(label_list, return_counts=True, return_index=True)
                # #print(label_unique,label_index,label_count)
                #
                #
                # for i in range(1):
                #     #一个label要使用的数组
                #     #result = np.empty(shape=[label_count[i],feature_num],dtype=np.str_)
                #     #一个label的索引在一个用户文件中
                #     start = label_index[i]
                #     end = label_index[i] + label_count[i]
                #     #一个label索引对应的原始数据
                #     data = user_data_file[start:end,:]
                #     #经纬度 以及时间
                #     lat_lon_time = data[:,[1,2,5]]
                #     #将user_id,经纬度赋值给结果数组
                #     #result[:,0:3] = data[:,0:3]
                #
                #     #计算特征  速度 加速度  开始点没有速度，第一个点没有加速度， 所以最后数组比原始数组少两个点
                #     for i in range(1,len(lat_lon_time)):
                #         dis = util.jwd2dis(lat_lon_time[i][0],lat_lon_time[i][1],lat_lon_time[i-1][0],lat_lon_time[i-1][1])
                #         t = util.timestamp2second(lat_lon_time[i],lat_lon_time[i-1])
                #
                #     print(lat_lon_time)



                # #user_data = user_data_file.readlines()
                #列名
                col_name = ["user_id","lat","lon","non-use","alt","timestamp","date","time","label","label_count"]
                #原始数据
                raw_data_df = pd.DataFrame(pd.read_csv(user_data_file,header=None,names=col_name))
                #结果列名
                result_col_name = ["user_id","lat","lon","speed_sec","acc_sec","std_speed","avg_speed","mean_acc","std_acc","head","head_mean","std_head","date","time","label","seg_label"]
                #结果数据
                result_df = pd.DataFrame(columns=result_col_name)

                #通过标签分组轨迹
                label_gp = raw_data_df.groupby(by=col_name[-1])

                for label_count,group in label_gp:
                    #print(group)
                    #print(len(group.index))
                    #temp_result = pd.DataFrame(columns = result_col_name)
                    #特征数组
                    #print("label_count",label_count)
                    if (group.index[-1] - group.index[0]) < 2:
                        print("丢弃本组数据")
                        continue
                    feature_arr = np.zeros(shape=[group.index[-1] - group.index[0] +1,feature_num],dtype=np.float64)
                    fangweijiao = np.zeros(shape=[group.index[-1] - group.index[0] +1],dtype=np.float64)
                    #print(group)
                    #print(len(group.index))
                    offset =  group.index[0]
                    for ii in  group.index[1:]:
                        #row_result = pd.Series(index=result_col_name)
                        dis = util.jwd2dis(group.loc[ii,"lat"],group.loc[ii,"lon"],group.loc[ii-1,"lat"],group.loc[ii-1,"lon"])
                        t = util.timestamp2second(group.loc[ii,"timestamp"],group.loc[ii-1,"timestamp"])
                        #速度
                        feature_arr[ii - offset][0] = dis/t
                        if(ii > offset+1):
                            #加速度
                            #a = (v1-v0)/t
                            feature_arr[ii- offset][1] = (feature_arr[ii- offset][0] - feature_arr[ii-1-offset][0]) / t

                        fangweijiao[ii-offset] = util.jwd2angle(group.loc[ii,"lat"],group.loc[ii,"lon"],group.loc[ii-1,"lat"],group.loc[ii-1,"lon"])

                    #方向转换  正数代表作，负数代表右
                    for k in range(2,len(fangweijiao)):
                        if fangweijiao[k] - fangweijiao[k-1] <= 180:
                            feature_arr[k][6] = fangweijiao[k] - fangweijiao[k-1]
                        else:
                            feature_arr[k][6] = -(360 - (fangweijiao[k] - fangweijiao[k-1]))

                    #0 放的是速度 1放的是加速度
                    avg_speed = np.mean(feature_arr[2:,0],axis=0)
                    acc_mean = np.mean(feature_arr[2:,1],axis=0)
                    std_speed = np.std(feature_arr[2:,0],axis=0)
                    std_acc = np.std(feature_arr[2:,1],axis=0)
                    head_mean = np.mean(np.abs(feature_arr[2:,6]),axis=0)
                    std_head = np.std(feature_arr[2:,6],axis=0)
                    feature_arr[2:,2] = std_speed
                    feature_arr[2:,3] = avg_speed
                    feature_arr[2:,4] = acc_mean
                    feature_arr[2:,5] = std_acc
                    feature_arr[2:,7] = head_mean
                    feature_arr[2:,8] = std_head
                    feature_arr = feature_arr[2:,:]

                    #print(feature_arr)
                    result = pd.DataFrame(columns=result_col_name)
                    #result["user_id"] = group["user_id"][2:len(group.index)]
                    start = group.index[0] + 2
                    end = group.index[-1]
                    result["user_id"] = group.loc[start:end,"user_id"]
                    result["lat"] = group.loc[start:end,"lat"]
                    result["lon"] = group.loc[start:end,"lon"]
                    #print(result.info(),length,feature_arr.shape)
                    result["speed_sec"] = feature_arr[:,0]
                    result["acc_sec"] = feature_arr[:,1]
                    result["std_speed"] = feature_arr[:,2]
                    result["avg_speed"] = feature_arr[:,3]
                    result["mean_acc"] = feature_arr[:,4]
                    result["std_acc"] = feature_arr[:,5]
                    result["head"] = feature_arr[:,6]
                    result["head_mean"] = feature_arr[:,7]
                    result["std_head"] = feature_arr[:,8]
                    result["date"] = group.loc[start:end,"date"]
                    result["time"] = group.loc[start:end,"time"]
                    result["label"] = util.switch_mode(group.loc[start,"label"])
                    result["seg_label"] = user_id +" " + str(group.loc[start,"label_count"])
                    #一组label最终结果dataframe
                    result_df = result_df.append(result)

                result_df.index = range(0,result_df.shape[0])
                #result_df.to_csv(datadir + user_id + "/user_features.csv", index=False)
                result_df.to_csv(datadir + user_id +"/user_features_interval_"+str(interval) +".csv",index=False,mode="w+")
                user_data_file.close()

        # 计算特征
    @staticmethod
    def caculate_feature_12(interval_list):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        feature_num = 12
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        for interval in interval_list:
            print("处理%d" % (interval))
            for user in user_list:
                user_id = user[0:3]
                user_data_name = datadir + user_id + "/userdata_interval_" + str(interval) + ".csv"
                # user_data_name = datadir + user_id + "/userdata.csv"
                print("开始处理", user_id)
                user_data_file = open(user_data_name, "r")

                # user_data_file = np.loadtxt(user_data_name,dtype=np.str,delimiter=",")
                # label_list = user_data_file[:,-1]
                # label_list = label_list.astype(int)
                # label_unique,label_index,label_count = np.unique(label_list, return_counts=True, return_index=True)
                # #print(label_unique,label_index,label_count)
                #
                #
                # for i in range(1):
                #     #一个label要使用的数组
                #     #result = np.empty(shape=[label_count[i],feature_num],dtype=np.str_)
                #     #一个label的索引在一个用户文件中
                #     start = label_index[i]
                #     end = label_index[i] + label_count[i]
                #     #一个label索引对应的原始数据
                #     data = user_data_file[start:end,:]
                #     #经纬度 以及时间
                #     lat_lon_time = data[:,[1,2,5]]
                #     #将user_id,经纬度赋值给结果数组
                #     #result[:,0:3] = data[:,0:3]
                #
                #     #计算特征  速度 加速度  开始点没有速度，第一个点没有加速度， 所以最后数组比原始数组少两个点
                #     for i in range(1,len(lat_lon_time)):
                #         dis = util.jwd2dis(lat_lon_time[i][0],lat_lon_time[i][1],lat_lon_time[i-1][0],lat_lon_time[i-1][1])
                #         t = util.timestamp2second(lat_lon_time[i],lat_lon_time[i-1])
                #
                #     print(lat_lon_time)

                # #user_data = user_data_file.readlines()
                # 列名
                col_name = ["user_id", "lat", "lon", "non-use", "alt", "timestamp", "date", "time", "label",
                            "label_count"]
                # 原始数据
                raw_data_df = pd.DataFrame(pd.read_csv(user_data_file, header=None, names=col_name))
                # 结果列名
                result_col_name = ["user_id", "lat", "lon", "speed_sec", "acc_sec", "std_speed", "avg_speed",
                                   "mean_acc", "std_acc", "head", "head_mean", "std_head","max_speed","max_acc","max_head", "date", "time", "label",
                                   "seg_label"]
                # 结果数据
                result_df = pd.DataFrame(columns=result_col_name)

                # 通过标签分组轨迹
                label_gp = raw_data_df.groupby(by=col_name[-1])

                for label_count, group in label_gp:
                    # print(group)
                    # print(len(group.index))
                    # temp_result = pd.DataFrame(columns = result_col_name)
                    # 特征数组
                    # print("label_count",label_count)
                    if (group.index[-1] - group.index[0]) < 2:
                        print("丢弃本组数据")
                        continue
                    feature_arr = np.zeros(shape=[group.index[-1] - group.index[0] + 1, feature_num],
                                           dtype=np.float64)
                    fangweijiao = np.zeros(shape=[group.index[-1] - group.index[0] + 1], dtype=np.float64)
                    # print(group)
                    # print(len(group.index))
                    offset = group.index[0]
                    for ii in group.index[1:]:
                        # row_result = pd.Series(index=result_col_name)
                        dis = util.jwd2dis(group.loc[ii, "lat"], group.loc[ii, "lon"], group.loc[ii - 1, "lat"],
                                           group.loc[ii - 1, "lon"])
                        t = util.timestamp2second(group.loc[ii, "timestamp"], group.loc[ii - 1, "timestamp"])
                        # 速度
                        feature_arr[ii - offset][0] = dis / t
                        if (ii > offset + 1):
                            # 加速度
                            # a = (v1-v0)/t
                            feature_arr[ii - offset][1] = (feature_arr[ii - offset][0] -
                                                           feature_arr[ii - 1 - offset][0]) / t

                        fangweijiao[ii - offset] = util.jwd2angle(group.loc[ii, "lat"], group.loc[ii, "lon"],
                                                                  group.loc[ii - 1, "lat"],
                                                                  group.loc[ii - 1, "lon"])

                    # 方向转换  正数代表作，负数代表右
                    #print(fangweijiao)
                    for k in range(2, len(fangweijiao)):
                        #print(fangweijiao[k],fangweijiao[k-1])
                        #print(fangweijiao[k] - fangweijiao[k-1])
                        if fangweijiao[k] >= fangweijiao[k-1]:

                            if fangweijiao[k] - fangweijiao[k - 1] <= 180:
                                feature_arr[k][6] = fangweijiao[k] - fangweijiao[k - 1]
                            else:
                                feature_arr[k][6] = -(360 - (fangweijiao[k] - fangweijiao[k - 1]))
                        else:
                            if fangweijiao[k-1] - fangweijiao[k] <=180:
                                feature_arr[k][6] = fangweijiao[k-1] - fangweijiao[k]
                            else:
                                feature_arr[k][6] = -(360 - (fangweijiao[k-1] - fangweijiao[k]))


                    # 0 放的是速度 1放的是加速度
                    avg_speed = np.mean(feature_arr[2:, 0], axis=0)
                    acc_mean = np.mean(feature_arr[2:, 1], axis=0)
                    std_speed = np.std(feature_arr[2:, 0], axis=0)
                    std_acc = np.std(feature_arr[2:, 1], axis=0)
                    head_mean = np.mean(np.abs(feature_arr[2:, 6]), axis=0)
                    std_head = np.std(feature_arr[2:, 6], axis=0)
                    max_speed = np.max(np.abs(feature_arr[2:,0]),axis=0)
                    max_acc = np.max(np.abs(feature_arr[2:,1]),axis=0)
                    max_head = np.max(np.abs(feature_arr[2:,6]),axis=0)
                    #print(feature_arr[2:,6])
                    feature_arr[2:, 2] = std_speed
                    feature_arr[2:, 3] = avg_speed
                    feature_arr[2:, 4] = acc_mean
                    feature_arr[2:, 5] = std_acc
                    feature_arr[2:, 7] = head_mean
                    feature_arr[2:, 8] = std_head
                    feature_arr[2:,9]  = max_speed
                    feature_arr[2:, 10]= max_acc
                    feature_arr[2:,11] = max_head
                    feature_arr = feature_arr[2:, :]

                    # print(feature_arr)
                    result = pd.DataFrame(columns=result_col_name)
                    # result["user_id"] = group["user_id"][2:len(group.index)]
                    start = group.index[0] + 2
                    end = group.index[-1]
                    result["user_id"] = group.loc[start:end, "user_id"]
                    result["lat"] = group.loc[start:end, "lat"]
                    result["lon"] = group.loc[start:end, "lon"]
                    # print(result.info(),length,feature_arr.shape)
                    result["speed_sec"] = feature_arr[:, 0]
                    result["acc_sec"] = feature_arr[:, 1]
                    result["std_speed"] = feature_arr[:, 2]
                    result["avg_speed"] = feature_arr[:, 3]
                    result["mean_acc"] = feature_arr[:, 4]
                    result["std_acc"] = feature_arr[:, 5]
                    result["head"] = feature_arr[:, 6]
                    result["head_mean"] = feature_arr[:, 7]
                    result["std_head"] = feature_arr[:, 8]
                    result["max_speed"] = feature_arr[:,9]
                    result["max_acc"] = feature_arr[:,10]
                    result["max_head"] = feature_arr[:,11]
                    result["date"] = group.loc[start:end, "date"]
                    result["time"] = group.loc[start:end, "time"]
                    result["label"] = util.switch_mode(group.loc[start, "label"])
                    result["seg_label"] = user_id + " " + str(group.loc[start, "label_count"])
                    # 一组label最终结果dataframe
                    result_df = result_df.append(result)

                result_df.index = range(0, result_df.shape[0])
                # result_df.to_csv(datadir + user_id + "/user_features.csv", index=False)
                result_df.to_csv(datadir + user_id + "/user_features_interval_" + str(interval) + ".csv",
                                 index=False, mode="w+")
                user_data_file.close()

    @staticmethod
    def caculate_feature_max_min():
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        feature_num = 10
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        for user in user_list:
            user_id = user[0:3]
            user_feature_name = datadir + user_id + "/user_features.csv"
            user_feature_file = open(user_feature_name,"r")
            user_feature_df = pd.DataFrame(pd.read_csv(user_feature_file))

            user_feature_max_min_name = datadir + user_id +"/user_features_max_min.csv"
            label_group = user_feature_df.groupby(by="label")

            #result = np.zeros(shape=[10,len(label_group)+1])
            result_df = pd.DataFrame(columns=["speed_sec","acc_sec","std_speed","avg_speed","mean_acc","max_or_min","label"])

            print(user_id)

            for name,group in label_group:
                #print(type(group))
                #series_max = group.iloc[:,[3,4,5,6,7]].idxmax()
                #series_min = group.iloc[:,[3,4,5,6,7]].idxmin()
                max = group.iloc[:,[3,4,5,6,7,-2]].max()
                min = group.iloc[:,[3,4,5,6,7,-2]].min()
                max["max_or_min"] = "max"
                min["max_or_min"] = "min"
                #max_list = max.tolist()
                #max_list.append("max")
                df_max = pd.DataFrame(max)
                df_max = df_max.T
                df_min = pd.DataFrame(min)
                df_min = df_min.T
                result_df = result_df.append(df_max)
                result_df = result_df.append(df_min)
                # df.append(pd.DataFrame(max))
                #dict = max.to_dict()
                #max.to_csv(user_feature_max_name,mode= "a+",index =True)
                #min.to_csv(user_feature_min_name,mode = "a+",index = True)
                # print(name)
                # print(group.describe())
                # print(group.iloc[:,[3,4,5,6,7]].quantile(0.95))
                # #print(group.loc[237777,"speed_sec"])
                # #print(series_max[[0,1]])
                # #print(type(list(series_max.index)))
                # #print(group.iloc[series_max,series_max.index])
                # max_list = []
                # min_list = []
                # for i in range(len(series_max)):
                #     #print(series_max[i])
                #     #print(series_max.index[i])
                #     #print(series_max.iloc[i])
                #     max_list.append(group.loc[series_max.iloc[i],series_max.index[i]])
                #     min_list.append(group.loc[series_min.iloc[i],series_min.index[i]])
                #
                # print(max_list,min_list)

            #print(result_df)
            result_df.to_csv(user_feature_max_min_name,index=False)
            user_feature_file.close()

        valiable_user_data.close()

    @staticmethod
    def caculate_all_max_min():
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        feature_num = 10
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        col_name = ["speed_sec", "acc_sec", "std_speed", "avg_speed", "mean_acc", "max_or_min", "label"]
        df = pd.DataFrame()
        #status = open(datadir+"status.csv","w+")


        for user in user_list:
            user_id = user[0:3]
            # user_features_max_min_name = datadir + user_id + "/user_features_max_min.csv"
            # user_features_max_min_file = open(user_features_max_min_name,"r")
            # # 原始数据
            # raw_data_df = pd.DataFrame(pd.read_csv(user_features_max_min_file))
            # max_min_df = max_min_df.append(raw_data_df)
            #
            # user_features_max_min_file.close()
            user_feature_file_name = datadir + user_id +"/user_features.csv"
            user_feature_file = open(user_feature_file_name,"r")
            raw_data_df = pd.DataFrame(pd.read_csv(user_feature_file))
            df = df.append(raw_data_df)

        df_label_groups = df.groupby("label")


        result_df = pd.DataFrame()
        for name,group in df_label_groups:
            df_gp_desc = group.iloc[:,[3,4,5,6,7]].describe()
            baifenwei_95 = group.iloc[:,[3,4,5,6,7]].quantile(0.95)
            baifenwei_96 = group.iloc[:,[3,4,5,6,7]].quantile(0.96)
            baifenwei_97 = group.iloc[:, [3, 4, 5, 6, 7]].quantile(0.97)
            baifenwei_98 = group.iloc[:, [3, 4, 5, 6, 7]].quantile(0.98)
            baifenwei_99 = group.iloc[:, [3, 4, 5, 6, 7]].quantile(0.99)
            #result_df = result_df.append(df_gp_desc)
            #print(name,"\n",baifenwei_95,baifenwei_96,baifenwei_97,baifenwei_98,baifenwei_99)
            file_name_99 = datadir + "baifenwei_99"  + ".csv"
            file_name_98 = datadir + "baifenwei_98" + ".csv"
            file_name_97 = datadir + "baifenwei_97" + ".csv"
            file_name_96 = datadir + "baifenwei_96" + ".csv"
            file_name_95 = datadir + "baifenwei_95" + ".csv"
            baifenwei_99.to_csv(file_name_99,mode = "a+")
            baifenwei_98.to_csv(file_name_98,mode = "a+")
            baifenwei_97.to_csv(file_name_97,mode = "a+")
            baifenwei_96.to_csv(file_name_96,mode = "a+")
            baifenwei_95.to_csv(file_name_95,mode = "a+")
            file_name = datadir+"status_label_" +str(name) + ".csv"
            df_gp_desc.to_csv(file_name,index=True,mode = "w+")


        #print(result_df)
        #result_df.to_csv(datadir+"status.csv",mode="w+")
        # max_min_groups = max_min_df.groupby(by = "max_or_min")
        #
        # max_group = max_min_groups.get_group(name="max")
        # min_group = max_min_groups.get_group(name="min")
        #
        # label_max_groups = max_group.groupby(by="label")
        # label_min_groups = min_group.groupby(by= "label")
        #
        # for name,group in label_max_groups:
        #     df_desc = group.describe()
        #     baifenwei_75 = df_desc.loc["75%"]
        #     baifenwei_25 = df_desc.loc["25%"]
        #     delta_Q = baifenwei_75 - baifenwei_25
        #     max = baifenwei_75 + delta_Q*1.5
        #     print(max)
        #for name,group in label_min_groups:
        #    print(name,group.describe())


        valiable_user_data.close()

    @staticmethod
    def features_status(interval_list):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        out_path = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/features_status/"
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()

        for interval in interval_list:
            print("处理%d" %(interval))
            users_df = pd.DataFrame()
            for user in user_list:
                user_id = user[0:3]
                # user_features_max_min_name = datadir + user_id + "/user_features_max_min.csv"
                # user_features_max_min_file = open(user_features_max_min_name,"r")
                # # 原始数据
                # raw_data_df = pd.DataFrame(pd.read_csv(user_features_max_min_file))
                # max_min_df = max_min_df.append(raw_data_df)
                #
                # user_features_max_min_file.close()
                user_feature_file_name = datadir + user_id +"/user_features_interval_" + str(interval)+".csv"
                user_feature_file = open(user_feature_file_name,"r")
                raw_data_df = pd.DataFrame(pd.read_csv(user_feature_file))
                users_df = users_df.append(raw_data_df)

            users_df.reset_index(drop=True)

            pd.DataFrame(users_df[param.SPEED_SEC].describe()).to_csv(out_path+"before_" +param.SPEED_SEC + ".csv")
            pd.DataFrame(users_df[param.AVG_SPEED].describe()).to_csv(out_path+"before_" +param.AVG_SPEED + ".csv")
            pd.DataFrame(users_df[param.STD_SPEED].describe()).to_csv(out_path+"before_" +param.STD_SPEED + ".csv")
            pd.DataFrame(users_df[param.ACC_SEC].describe()).to_csv(out_path+"before_" +param.ACC_SEC + ".csv")
            pd.DataFrame(users_df[param.MEAN_ACC].describe()).to_csv(out_path+"before_" +param.MEAN_ACC + ".csv")
            pd.DataFrame(users_df[param.STD_ACC].describe()).to_csv(out_path+"before_" +param.STD_ACC + ".csv")
            pd.DataFrame(users_df[param.HEAD].describe()).to_csv(out_path+"before_" +param.HEAD + ".csv")
            pd.DataFrame(users_df[param.HEAD_MEAN].describe()).to_csv(out_path+"before_" +param.HEAD_MEAN + ".csv")
            pd.DataFrame(users_df[param.STD_HEAD].describe()).to_csv(out_path+"before_" +param.STD_HEAD + ".csv")



            speed_sec = pd.DataFrame(Data.filter_box_quantile(users_df["speed_sec"], FILTER_K)).describe()
            acc_sec = pd.DataFrame(Data.filter_box_quantile(users_df["acc_sec"], FILTER_K)).describe()
            avg_speed = pd.DataFrame(Data.filter_box_quantile(users_df["avg_speed"], FILTER_K)).describe()
            std_speed = pd.DataFrame(Data.filter_box_quantile(users_df["std_speed"], FILTER_K)).describe()
            mean_acc = pd.DataFrame(Data.filter_box_quantile(users_df["mean_acc"], FILTER_K)).describe()
            std_acc = pd.DataFrame(Data.filter_box_quantile(users_df["std_acc"], FILTER_K)).describe()
            head = pd.DataFrame(Data.filter_box_quantile(users_df["head"], FILTER_K)).describe()
            head_mean = pd.DataFrame(Data.filter_box_quantile(users_df["head_mean"], FILTER_K)).describe()
            std_head = pd.DataFrame(Data.filter_box_quantile(users_df["std_head"], FILTER_K)).describe()

            pd.DataFrame(speed_sec).to_csv(out_path+"after_"+param.SPEED_SEC +".csv")
            pd.DataFrame(avg_speed).to_csv(out_path+"after_"+param.AVG_SPEED +".csv")
            pd.DataFrame(std_speed).to_csv(out_path+"after_"+param.STD_SPEED +".csv")
            pd.DataFrame(acc_sec).to_csv(out_path+"after_"+param.ACC_SEC +".csv")
            pd.DataFrame(mean_acc).to_csv(out_path+"after_"+param.MEAN_ACC +".csv")
            pd.DataFrame(std_acc).to_csv(out_path+"after_"+param.STD_ACC +".csv")
            pd.DataFrame(head).to_csv(out_path+"after_"+param.HEAD +".csv")
            pd.DataFrame(head_mean).to_csv(out_path+"after_"+param.HEAD_MEAN +".csv")
            pd.DataFrame(std_head).to_csv(out_path+"after_"+param.STD_HEAD +".csv")

    #离散化
    @staticmethod
    def discretization(interval_list):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        out_path = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/features_95_15/"
        feature_num = 9
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        #col_name = ["speed_sec", "acc_sec", "std_speed", "avg_speed", "mean_acc", "max_or_min", "label"]
        #所有数据

        # status = open(datadir+"status.csv","w+")
        for interval in interval_list:
            print("处理%d" %(interval))
            users_df = pd.DataFrame()
            for user in user_list:
                user_id = user[0:3]
                # user_features_max_min_name = datadir + user_id + "/user_features_max_min.csv"
                # user_features_max_min_file = open(user_features_max_min_name,"r")
                # # 原始数据
                # raw_data_df = pd.DataFrame(pd.read_csv(user_features_max_min_file))
                # max_min_df = max_min_df.append(raw_data_df)
                #
                # user_features_max_min_file.close()
                user_feature_file_name = datadir + user_id +"/user_features_interval_" + str(interval)+".csv"
                user_feature_file = open(user_feature_file_name,"r")
                raw_data_df = pd.DataFrame(pd.read_csv(user_feature_file))
                users_df = users_df.append(raw_data_df)

            users_df.reset_index(drop=True)
            # print("离散化")
            #
            # file = open(out_path+"status"+str(interval)+".txt",mode="w+")
            # file.write("interval_%d \n"%(interval))
            # for i in [0,0.95,0.96,0.97,0.98,0.99]:
            #     file.write("%s %f  %f\n" % (param.SPEED_SEC,i,users_df[param.SPEED_SEC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.AVG_SPEED,i,users_df[param.AVG_SPEED].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.STD_SPEED,i,users_df[param.STD_SPEED].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.ACC_SEC,i,users_df[param.ACC_SEC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.MEAN_ACC,i,users_df[param.MEAN_ACC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.STD_ACC,i,users_df[param.STD_ACC].quantile(i)))
            #     file.write("\n")
            #
            # file.close()
            speed_sec = pd.DataFrame(Data.equal_width(users_df["speed_sec"],WIDTH))
            acc_sec = pd.DataFrame(Data.equal_width(users_df["acc_sec"],WIDTH))
            avg_speed = pd.DataFrame(Data.equal_width(users_df["avg_speed"],WIDTH))
            std_speed = pd.DataFrame(Data.equal_width(users_df["std_speed"],WIDTH))
            mean_acc = pd.DataFrame(Data.equal_width(users_df["mean_acc"],WIDTH))
            std_acc = pd.DataFrame(Data.equal_width(users_df["std_acc"],WIDTH))
            head = pd.DataFrame(Data.equal_width(users_df["head"],WIDTH))
            head_mean = pd.DataFrame(Data.equal_width(users_df["head_mean"],WIDTH))
            std_head = pd.DataFrame(Data.equal_width(users_df["std_head"],WIDTH))

            print("连接矩阵")
            #features_en = np.concatenate((speed_sec,avg_speed,std_speed,acc_sec,mean_acc,std_acc),axis=1)
            result_df = pd.concat([speed_sec,avg_speed,std_speed,acc_sec,mean_acc,std_acc,head,head_mean,std_head],axis=1)

            #result_df = pd.DataFrame(features_en)
            result_df["label"] = users_df["label"].values
            result_df["seg_label"] = users_df["seg_label"].values
            #col_name = result_df.columns.tolist()
            #col_name.insert(col_name.index(0),"user_id")
            #result_df.reindex(columns=col_name)
            result_df["user_id"] = users_df["user_id"].values
            #result_df    columns =[userid(1),speed_sec(width),avg_speed(width),std_speed(width),acc_sec(width),mean_acc(width),label(1),seg_label(1)]

            #result_file = open(datadir+"user_features_data_en.csv",mode="w+")
            result_df.to_csv(out_path+"user_features_data_en_1_interval_"+str(interval)+".csv",mode="w+",header=True,index=False)

            valiable_user_data.close()

    @staticmethod
    def discretization_12(interval_list):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        out_path = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/features_12_95_30/"
        feature_num = 12
        valiable_user_data = open("./data/have_label_user.txt", "r")
        user_list = valiable_user_data.readlines()
        # col_name = ["speed_sec", "acc_sec", "std_speed", "avg_speed", "mean_acc", "max_or_min", "label"]
        # 所有数据

        # status = open(datadir+"status.csv","w+")
        for interval in interval_list:
            print("处理%d" % (interval))
            users_df = pd.DataFrame()
            for user in user_list:
                user_id = user[0:3]
                # user_features_max_min_name = datadir + user_id + "/user_features_max_min.csv"
                # user_features_max_min_file = open(user_features_max_min_name,"r")
                # # 原始数据
                # raw_data_df = pd.DataFrame(pd.read_csv(user_features_max_min_file))
                # max_min_df = max_min_df.append(raw_data_df)
                #
                # user_features_max_min_file.close()
                user_feature_file_name = datadir + user_id + "/user_features_interval_" + str(interval)+ ".csv"
                user_feature_file = open(user_feature_file_name, "r")
                raw_data_df = pd.DataFrame(pd.read_csv(user_feature_file))
                users_df = users_df.append(raw_data_df)

            users_df.reset_index(drop=True)
            # print("离散化")
            #
            # file = open(out_path+"status"+str(interval)+".txt",mode="w+")
            # file.write("interval_%d \n"%(interval))
            # for i in [0,0.95,0.96,0.97,0.98,0.99]:
            #     file.write("%s %f  %f\n" % (param.SPEED_SEC,i,users_df[param.SPEED_SEC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.AVG_SPEED,i,users_df[param.AVG_SPEED].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.STD_SPEED,i,users_df[param.STD_SPEED].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.ACC_SEC,i,users_df[param.ACC_SEC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.MEAN_ACC,i,users_df[param.MEAN_ACC].quantile(i)))
            #     file.write("%s %f  %f\n" % (param.STD_ACC,i,users_df[param.STD_ACC].quantile(i)))
            #     file.write("\n")
            #
            # file.close()
            speed_sec = pd.DataFrame(Data.equal_width(users_df["speed_sec"], WIDTH))
            acc_sec = pd.DataFrame(Data.equal_width(users_df["acc_sec"], WIDTH))
            avg_speed = pd.DataFrame(Data.equal_width(users_df["avg_speed"], WIDTH))
            std_speed = pd.DataFrame(Data.equal_width(users_df["std_speed"], WIDTH))
            mean_acc = pd.DataFrame(Data.equal_width(users_df["mean_acc"], WIDTH))
            std_acc = pd.DataFrame(Data.equal_width(users_df["std_acc"], WIDTH))
            head = pd.DataFrame(Data.equal_width(users_df["head"], WIDTH))
            head_mean = pd.DataFrame(Data.equal_width(users_df["head_mean"], WIDTH))
            std_head = pd.DataFrame(Data.equal_width(users_df["std_head"], WIDTH))
            max_speed = pd.DataFrame(Data.equal_width(users_df["max_speed"], WIDTH))
            max_acc = pd.DataFrame(Data.equal_width(users_df["max_acc"], WIDTH))
            max_head = pd.DataFrame(Data.equal_width(users_df["max_head"], WIDTH))

            print("连接矩阵")
            # features_en = np.concatenate((speed_sec,avg_speed,std_speed,acc_sec,mean_acc,std_acc),axis=1)
            result_df = pd.concat(
                [speed_sec, avg_speed, std_speed, acc_sec, mean_acc, std_acc, head, head_mean, std_head,max_speed,max_acc,max_head], axis=1)

            # result_df = pd.DataFrame(features_en)
            result_df["label"] = users_df["label"].values
            result_df["seg_label"] = users_df["seg_label"].values
            # col_name = result_df.columns.tolist()
            # col_name.insert(col_name.index(0),"user_id")
            # result_df.reindex(columns=col_name)
            result_df["user_id"] = users_df["user_id"].values
            # result_df    columns =[userid(1),speed_sec(width),avg_speed(width),std_speed(width),acc_sec(width),mean_acc(width),label(1),seg_label(1)]

            # result_file = open(datadir+"user_features_data_en.csv",mode="w+")
            result_df.to_csv(out_path + "user_features_data_en_1_interval_" + str(interval) + ".csv", mode="w+",
                             header=True, index=False)

            valiable_user_data.close()

    #盒状过滤
    @staticmethod
    def filter_box_quantile(x,k):
        print(x.name)
        #不同的特征不同过滤
        min = 0
        max = 0
        if x.name == param.SPEED_SEC or x.name == param.AVG_SPEED \
                or x.name == param.STD_SPEED or x.name == param.MEAN_ACC  or x.name == param.STD_ACC\
                or x.name == param.HEAD_MEAN or x.name == param.STD_HEAD:
            min = x.quantile(0)
            max = x.quantile(FENWEI_MAX)
        elif x.name == param.ACC_SEC or x.name == param.HEAD:
            min = x.quantile(0.01)
            max = x.quantile(FENWEI_MAX)
        n = len(x.index)
        y = np.array(x.values)

        for i in range(k+1,n-k):

            if y[i] >min and y[i] <max:
                continue
            y[i] = np.median(y[i-k:i+k])

            if y[i] > max:
                y[i] = max
            if y[i] < min:
                y[i] = min
        series_y = pd.Series(data=y)

        return series_y

    #等宽离散
    @staticmethod
    def equal_width(x,width):
        x = Data.filter_box_quantile(x,10)

        min = x.min()
        max = x.max()
        interval = (max - min + 0.001)/width
        x_arr = np.array(x.values)
        x_arr = (x_arr - min) / interval
        x_arr = np.floor(x_arr).astype(np.int64)
        x_result = np.zeros(shape=[len(x_arr),width],dtype=np.int32)
        for i in  range(len(x_arr)):
            x_result[i][x_arr[i]] = 1

        return x_result

    #制作npy文件
    @staticmethod
    def create_npy(interval):
        datadir = "G:/新建文件夹/Geolife Trajectories 1.3/Data/"
        self_data_dir = "./data/transportation_feature_en_1_interval_2/"
        user_data_file_name = datadir + "user_features_data_en_1_interval_"+str(interval)+".csv"
        user_data_file = open(user_data_file_name, "r")
        user_data_df = pd.DataFrame(pd.read_csv(user_data_file))
        classes = 4
        #0-99 特征one-hot编码后数据 100 label 101 seg_label 102 user_id
        user_data_label_groups = user_data_df.groupby(by="label")

        for name,group in user_data_label_groups:
            #if int(name) < 7:
            #    continue
            print("处理label  ",name)
            mode_file_name = self_data_dir + "transportation_mode" + str(name) +".npy"
            features_arr = np.array(group.iloc[:,0:100])
            seg_label_arr = np.array(group.iloc[:,-2])
            seg_label_unique,seg_label_index,seg_label_count = np.unique(seg_label_arr,return_index=True,return_counts=True)
            index_file_name = self_data_dir + "transportation_mode_" + str(name) +"_seg_index.csv"
            index_df = pd.DataFrame()
            index_df["seg_label_unique"] = seg_label_unique
            index_df["seg_label_index"] = seg_label_index.astype(np.int32)
            index_df["seg_label_count"] = seg_label_count.astype(np.int32)
            index_df = index_df.sort_values(by="seg_label_index")

            index_df.to_csv(index_file_name,mode="w+",index=False)
            del index_df
            del seg_label_arr
            np.save(mode_file_name,features_arr)



        user_data_file.close()

        #user_data_df_classes_4 = user_data_df[user_data_df["label"]<4]
        #data_classes_4_groups = user_data_df_classes_4.groupby(by="label")
        #for name,group in data_classes_4_groups:

    #切割序列为指定长度
    @staticmethod
    def slice_seq(x,index,exp_seq_len):
        #index 第一维是索引，第二维是长度

        #特征长度
        features_len = x.shape[1]
        #每一段可以切出的序列个数
        seq_num_list = np.array([math.ceil(i) for i in (index[1]/exp_seq_len)])
        #总序列个数
        num_total_seq = int(sum(seq_num_list))
        #结果矩阵
        new_data = np.zeros(shape=[num_total_seq,exp_seq_len,features_len],dtype=np.float64)
        #new_label = np.zeros(shape=[num_total_seq,exp_seq_len])
        new_index = np.zeros(shape=[2,num_total_seq],dtype=np.int64)

        count = 0
        for i in range(len(seq_num_list)):
            #该段轨迹的长度
            seg_len = index[1][i]
            #索引开始
            seg_start = index[0][i]
            seg_end = seg_start + seg_len
            #二维数组
            seg_data = x[seg_start:seg_end]

            num_full_seq = seg_len // exp_seq_len
            if num_full_seq:
                full_seq = seg_data[0:num_full_seq * exp_seq_len].reshape((num_full_seq, exp_seq_len, features_len))
                new_data[count:(count + num_full_seq)] = full_seq
                #new_label[count:(count + num_full_seq)] = full_lab
                new_index[0][count:(count + num_full_seq)] = i
                new_index[1][count:(count + num_full_seq)] = exp_seq_len
                count += num_full_seq
            #如果序列没有对齐
            if num_full_seq <seq_num_list[i]:
                remain_seq = np.zeros((exp_seq_len, features_len))
                remain_seq[0:(seg_len - num_full_seq * exp_seq_len)] = seg_data[num_full_seq * exp_seq_len:seg_len]
                new_data[count] = remain_seq
                #new_label[count] = remain_lab
                new_index[0][count] = i
                new_index[1][count] = seg_len - num_full_seq * exp_seq_len
                count += 1
        return (new_data,new_index)

    #扩展数据  将原始seq打乱成新数据
    @staticmethod
    def expand_data_npy(classes,len_features):
        data_path  = "./data/transportation_feature_en_1_interval_1&2/"
        out_data_path = "./data/transportation_feature_en_1_interval_1&2_expand_all/"
        data_file_name_exp = data_path + "transportation_mode"
        for i in range(classes):
            print("处理" + str(i))
            # data_file  = data_file_name +str(i) +".npy"
            index_df = pd.DataFrame(pd.read_csv(data_file_name_exp + "_" + str(i) + "_seg_index.csv"))
            features_arr = np.load(data_file_name_exp + str(i) + ".npy")
            features_arr = features_arr[:, 0:len_features]
            index_arr = np.array(index_df.iloc[:, [1, 2]].T)
            # index shape = [2,总个数]
            # 第一维是第几段轨迹 第二维是在固定长度为exp_seq_len中的实际长度
            # data shape =[seq_nums,exp_seq_len,feature_len]
            features_arr_shuffle = np.zeros(shape=features_arr.shape,dtype=features_arr.dtype)

            start = 0
            end = 0
            for k in range(index_arr.shape[1] -1):
                perm = np.random.permutation(range(index_arr[0][k],index_arr[0][k+1]))
                end = start + index_arr[1][k]
                features_arr_shuffle[start:end,:] = features_arr[perm,:]
                start = end
            #连接新的矩阵
            features_arr_all = np.concatenate((features_arr,features_arr_shuffle),axis=0)
            #构造新的index
            index_df_expand = index_df.copy()
            index_df_expand["seg_label_index"] = index_df["seg_label_index"] + features_arr.shape[0]
            index_df_all = index_df.append(index_df_expand)

            features_arr_file_name = out_data_path + "transportation_mode" + str(i) +".npy"
            index_arr_file_name = out_data_path + "transportation_mode_" + str(i) + "_seg_index.csv"
            np.save(features_arr_file_name,features_arr_all)
            index_df_all.to_csv(index_arr_file_name,index = False)

    #制作所有数据的npz文件  包括原始数据与混淆数据
    @staticmethod
    def create_all_data_npy(classes,len_features):
        conf = config.Config("data/config.json")
        log_path = "./logdir/transportation_feature_en_1_expand/"
        data_path = "./data/transportation_feature_en_1_expand/"
        # 分训练集与测试集 验证集 8：1：1
        train_data_all = None
        train_label_all = None
        train_early_all = None
        valid_data_all = None
        valid_label_all = None
        valid_early_all = None
        test_data_all = None
        test_label_all = None
        test_early_all = None
        features_arr_list = []
        index_arr_list = []
        label_arr_list = []
        data_file_name_exp = data_path + "transportation_mode"
        for i in range(classes):
            print("加载" + str(i))
            # data_file  = data_file_name +str(i) +".npy"
            index_df = pd.DataFrame(pd.read_csv(data_file_name_exp + "_" + str(i) + "_seg_index.csv"))
            features_arr = np.load(data_file_name_exp + str(i) + ".npy")
            features_arr = features_arr[:, 0:len_features]
            index_arr = np.array(index_df.iloc[:, [1, 2]].T)
            # index shape = [2,总个数]
            # 第一维是第几段轨迹 第二维是在固定长度为exp_seq_len中的实际长度
            # data shape =[seq_nums,exp_seq_len,feature_len]   切出相等的数据长度 不足的padding
            (data, index_arr) = Data.slice_seq(features_arr, index_arr, conf.exp_seq_len)
            # 切割后删除features_arr index
            del features_arr
            del index_df
            label_arr = np.zeros(shape=[index_arr.shape[1]], dtype=np.int32)
            label_arr[:] = i
            # features_arr_list.append(data)
            # index_arr_list.append(index)
            # label_arr_list.append(label)
            # 划分训练集，验证集，测试集
            print("划分训练集，验证集，测试集   " + str(i))
            seq_nums = index_arr.shape[1]
            # 控制变量
            np.random.seed(2)
            index_perm = np.random.permutation(range(seq_nums))
            train_count = int(np.floor(seq_nums * 0.8))
            valid_count = int(np.floor(seq_nums * 0.9))
            test_count = seq_nums
            train_index = index_perm[0:train_count]
            valid_index = index_perm[train_count + 1:valid_count]
            test_index = index_perm[valid_count + 1:seq_nums]

            # train_set valid_set test_set
            train_data = data[train_index, :, :]
            train_label = label_arr[train_index]
            train_early = index_arr[1, train_index]

            valid_data = data[valid_index, :, :]
            valid_label = label_arr[valid_index]
            valid_early = index_arr[1, valid_index]

            test_data = data[test_index, :, :]
            test_label = label_arr[test_index]
            test_early = index_arr[1, test_index]

            # 删除读取到的data.
            del data
            del label_arr
            del index_arr

            if train_data_all is None:
                train_data_all = train_data
                train_label_all = train_label
                train_early_all = train_early

                valid_data_all = valid_data
                valid_label_all = valid_label
                valid_early_all = valid_early

                test_data_all = test_data
                test_label_all = test_label
                test_early_all = test_early
            else:
                train_data_all = np.concatenate((train_data_all, train_data), axis=0)
                train_label_all = np.concatenate((train_label_all, train_label), axis=0)
                train_early_all = np.concatenate((train_early_all, train_early), axis=0)

                valid_data_all = np.concatenate((valid_data_all, valid_data), axis=0)
                valid_label_all = np.concatenate((valid_label_all, valid_label), axis=0)
                valid_early_all = np.concatenate((valid_early_all, valid_early), axis=0)

                test_data_all = np.concatenate((test_data_all, test_data), axis=0)
                test_label_all = np.concatenate((test_label_all, test_label), axis=0)
                test_early_all = np.concatenate((test_early_all, test_early), axis=0)
        # 打乱数据
        np.random.seed(1)
        train_perm = np.random.permutation(range(train_early_all.shape[0]))
        np.random.seed(1)
        valid_perm = np.random.permutation(range(valid_early_all.shape[0]))
        np.random.seed(1)
        test_perm = np.random.permutation(range(test_early_all.shape[0]))

        # shape=[序列长度，总个数，特征长度]   TimeMajor
        train_data_all = np.transpose(train_data_all, [1, 0, 2])
        valid_data_all = np.transpose(valid_data_all, [1, 0, 2])
        test_data_all = np.transpose(test_data_all, [1, 0, 2])

        train_data_all = train_data_all[:, train_perm, :]
        train_label_all = train_label_all[train_perm]
        train_early_all = train_early_all[train_perm]

        valid_data_all = valid_data_all[:, valid_perm, :]
        valid_label_all = valid_label_all[valid_perm]
        valid_early_all = valid_early_all[valid_perm]

        test_data_all = test_data_all[:, test_perm, :]
        test_label_all = test_label_all[test_perm]
        test_early_all = test_early_all[test_perm]

        train_data_file = data_path + "train_data_set.npz"
        np.savez(train_data_file,train_data = train_data_all,train_label = train_label_all,train_early = train_early_all)
        del train_data_all
        del train_label_all
        del train_early_all

        valid_data_file = data_path + "valid_data_set.npz"
        np.savez(valid_data_file, valid_data=valid_data_all, valid_label=valid_label_all, valid_early=valid_early_all)
        del valid_data_all
        del valid_label_all
        del valid_early_all
        test_data_file = data_path + "test_data_set.npz"
        np.savez(test_data_file, test_data=test_data_all, test_label=test_label_all, test_early=test_early_all)

    #连接数据
    @staticmethod
    def concat_data(classes,len_features):
        data_path1 = "./data/transportation_feature_en_1/"
        data_path2 = "./data/transportation_feature_en_1_interval_2/"
        out_data_path = "./data/transportation_feature_en_1_interval_1&2/"
        data_file_name_exp1 = data_path1 + "transportation_mode"
        data_file_name_exp2 = data_path2 + "transportation_mode"
        for i in range(1,4):
            index_df1 = pd.DataFrame(pd.read_csv(data_file_name_exp1 + "_" + str(i) + "_seg_index.csv"))
            features_arr1 = np.load(data_file_name_exp1 + str(i) + ".npy")
            features_arr1 = features_arr1[:, 0:len_features]
            #index_arr1 = np.array(index_df1.iloc[:, [1, 2]].T)

            index_df2 = pd.DataFrame(pd.read_csv(data_file_name_exp2 + "_" + str(i) + "_seg_index.csv"))
            features_arr2 = np.load(data_file_name_exp2 + str(i) + ".npy")
            features_arr2 = features_arr2[:, 0:len_features]
            #index_arr2 = np.array(index_df2.iloc[:, [1, 2]].T)

            index_df2["seg_label_index"] = index_df2["seg_label_index"] + features_arr1.shape[0]
            index_df_all = index_df1.append(index_df2)
            index_file_name = out_data_path + "transportation_mode_" + str(i) +"_seg_index.csv"
            index_df_all.to_csv(index_file_name, mode="w+", index=False)

            features_arr_all = np.concatenate((features_arr1,features_arr2),axis=0)
            del features_arr1
            del features_arr2
            mode_file_name = out_data_path + "transportation_mode"+str(i)+".npy"
            np.save(mode_file_name,features_arr_all)

    @staticmethod
    def _int64_feature(value):
        return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))

    @staticmethod
    def _bytes_feature(value):
        return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))

    @staticmethod
    def _float_feature(value):
        return tf.train.Feature(float_list=tf.train.FloatList(value=[value]))

    #制作tfrecord 以段分类
    @staticmethod
    def make_tfrecord(interval_list):
        data_dir = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/"
        for interval in interval_list:
            print("处理"+str(interval))
            # train_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_train.tfrecords")
            # valid_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_valid.tfrecords")
            # test_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_test.tfrecords")
            data_file_name = data_dir + "user_features_data_en_1_interval_" + str(interval) + ".csv"
            data_file = open(data_file_name,mode="r")
            data_df = pd.DataFrame(pd.read_csv(data_file))

            data_label_groups = data_df.groupby(by="label")
            k = 0
            for label_name,label_group in data_label_groups:

                # if k < 6:
                #     k+=1
                #     continue
                # if k > 5:
                #     break
                file_group_count = 0

                print("处理label"+str(label_name))
                train_writer = tf.python_io.TFRecordWriter(
                    "G:/all_data/tfrecords/interval_" + str(interval)+"_label_"+str(label_name) + "_train_0.tfrecords")
                valid_writer = tf.python_io.TFRecordWriter(
                    "G:/all_data/tfrecords/interval_" + str(interval) +"_label_"+str(label_name)+ "_valid_0.tfrecords")
                test_writer = tf.python_io.TFRecordWriter(
                    "G:/all_data/tfrecords/interval_" + str(interval)+"_label_"+str(label_name) + "_test_0.tfrecords")
                seg_groups = label_group.groupby(by="seg_label")
                count = 0
                for seg_name,seg_group in seg_groups:
                    #seg_group 存放每段的轨迹点的特征，每个特征长30
                    speed_sec = np.array(seg_group.iloc[:,0:1*WIDTH])
                    avg_speed = np.array(seg_group.iloc[:1*WIDTH:2*WIDTH])
                    std_speed = np.array(seg_group.iloc[:,2*WIDTH:3*WIDTH])
                    acc_sec = np.array(seg_group.iloc[:, 3 * WIDTH:4 * WIDTH])
                    mean_acc = np.array(seg_group.iloc[:, 4 * WIDTH:5 * WIDTH])
                    std_acc = np.array(seg_group.iloc[:, 5 * WIDTH:6 * WIDTH])
                    feature = {
                        FeatureName.SPEED_SEC.value : Data._bytes_feature(speed_sec.tobytes()),
                        FeatureName.AVG_SPEED.value : Data._bytes_feature(avg_speed.tobytes()),
                        FeatureName.STD_SPEED.value : Data._bytes_feature(std_speed.tobytes()),
                        FeatureName.ACC_SEC.value   : Data._bytes_feature(acc_sec.tobytes()),
                        FeatureName.MEAN_ACC.value  : Data._bytes_feature(mean_acc.tobytes()),
                        FeatureName.STD_ACC.value   : Data._bytes_feature(std_acc.tobytes()),
                        "label":Data._int64_feature(label_name)
                    }
                    example = tf.train.Example(features = tf.train.Features(feature = feature))

                    if count % 1000 == 0 and count > 0:
                        train_writer.close()
                        valid_writer.close()
                        test_writer.close()
                        sys.stdout.flush()
                        file_group_count += 1

                        train_writer = tf.python_io.TFRecordWriter(
                            "G:/all_data/tfrecords/interval_" + str(interval) + "_label_" + str(
                                label_name) + "_train_" + str(file_group_count)+ ".tfrecords")
                        valid_writer = tf.python_io.TFRecordWriter(
                            "G:/all_data/tfrecords/interval_" + str(interval) + "_label_" + str(
                                label_name) + "_valid_" + str(file_group_count)+ ".tfrecords")
                        test_writer = tf.python_io.TFRecordWriter(
                            "G:/all_data/tfrecords/interval_" + str(interval) + "_label_" + str(
                                label_name) + "_test_" + str(file_group_count)+ ".tfrecords")


                    t = count % 10
                    if t >=0 and t <8 :
                        train_writer.write(example.SerializeToString())
                    elif t == 8:
                        valid_writer.write(example.SerializeToString())
                    else:
                        test_writer.write(example.SerializeToString())

                    count += 1
                k+=1
                train_writer.close()
                valid_writer.close()
                test_writer.close()
                sys.stdout.flush()

    #补零 规定长度 未分开
    @staticmethod
    def pad_seqs(x,exp_seq_len):
        seq_nums = int(np.ceil(x.shape[0]/exp_seq_len))
        seq_len = x.shape[0]
        early = np.zeros([seq_nums],dtype=np.int64)

        remain_len = seq_len % exp_seq_len
        if remain_len != 0:
            x_pad = np.pad(x,[[0,exp_seq_len-remain_len],[0,0]],"constant",constant_values=0)
            early[0:seq_nums-1] = exp_seq_len
            early[-1] = remain_len
            return x_pad,early
        else:
            early[:] = exp_seq_len
            return x,early

    #未完成
    @staticmethod
    def pad_slice_seqs(x,exp_seq_len):
        #未完成
        seq_nums = int(np.ceil(x.shape[0] / exp_seq_len))
        seq_len = x.shape[0]
        early = np.zeros([seq_nums], dtype=np.int32)
        remain_len = seq_len % exp_seq_len
        full_seq_nums = seq_len // exp_seq_len
        pass

    #制作规定长度的tfrecord
    @staticmethod
    def make_tfrecord_seq(interval_list,exp_seq_len):
        data_dir = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/"
        out_path = "G:/all_data/tfrecords/"
        for interval in interval_list:
            print("处理" + str(interval))
            # train_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_train.tfrecords")
            # valid_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_valid.tfrecords")
            # test_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_test.tfrecords")
            data_file_name = data_dir + "user_features_data_en_1_interval_" + str(interval) + ".csv"
            data_file = open(data_file_name, mode="r")
            data_df = pd.DataFrame(pd.read_csv(data_file))

            data_label_groups = data_df.groupby(by="label")
            k = 0
            for label_name, label_group in data_label_groups:

                # if k < 7:
                #     k+=1
                #     continue
                if k > 3:
                    return
                file_group_count = 0
                print("处理label" + str(label_name))
                train_writer = tf.python_io.TFRecordWriter(
                    out_path + "interval_"+str(interval) + "_label_" + str(
                        label_name) + "_train_0.tfrecords")
                valid_writer = tf.python_io.TFRecordWriter(
                    out_path + "interval_"+ str(interval) + "_label_" + str(
                        label_name) + "_valid_0.tfrecords")
                test_writer = tf.python_io.TFRecordWriter(
                    out_path + "interval_"+ str(interval) + "_label_" + str(label_name) + "_test_0.tfrecords")
                seg_groups = label_group.groupby(by="seg_label")
                count = 0
                for seg_name, seg_group in seg_groups:
                    # seg_group 存放每段的轨迹点的特征，每个特征长30
                    speed_sec = np.array(seg_group.iloc[:, 0 : 1 * WIDTH],dtype=np.int64)
                    avg_speed = np.array(seg_group.iloc[:, 1* WIDTH : 2 * WIDTH],dtype=np.int64)
                    std_speed = np.array(seg_group.iloc[:, 2* WIDTH : 3 * WIDTH],dtype=np.int64)
                    acc_sec = np.array(seg_group.iloc[:, 3* WIDTH : 4 * WIDTH],dtype=np.int64)
                    mean_acc = np.array(seg_group.iloc[:, 4* WIDTH : 5 * WIDTH],dtype=np.int64)
                    std_acc = np.array(seg_group.iloc[:, 5* WIDTH : 6 * WIDTH],dtype=np.int64)

                    speed_sec_pad,speed_sec_early = Data.pad_seqs(speed_sec,exp_seq_len)
                    avg_speed_pad,avg_speed_early = Data.pad_seqs(avg_speed,exp_seq_len)
                    std_speed_pad,std_speed_early = Data.pad_seqs(std_speed,exp_seq_len)
                    acc_sec_pad,acc_sec_early = Data.pad_seqs(acc_sec,exp_seq_len)
                    mean_acc_pad,mean_acc_early = Data.pad_seqs(mean_acc,exp_seq_len)
                    std_acc_pad,std_acc_early = Data.pad_seqs(std_acc,exp_seq_len)

                    label = np.zeros(speed_sec_early.shape,np.int64)
                    label[:] = int(label_name)

                    for i in range(len(speed_sec_early)):
                        start = i*exp_seq_len
                        end = (i+1)*exp_seq_len

                        feature = {
                            param.SPEED_SEC: Data._bytes_feature(speed_sec_pad[start:end].tobytes()),
                            param.AVG_SPEED: Data._bytes_feature(avg_speed_pad[start:end].tobytes()),
                            param.STD_SPEED: Data._bytes_feature(std_speed_pad[start:end].tobytes()),
                            param.ACC_SEC: Data._bytes_feature(acc_sec_pad[start:end].tobytes()),
                            param.MEAN_ACC: Data._bytes_feature(mean_acc_pad[start:end].tobytes()),
                            param.STD_ACC: Data._bytes_feature(std_acc_pad[start:end].tobytes()),
                            param.EARLY:Data._int64_feature(speed_sec_early[i]),
                            param.LABEL: Data._int64_feature(label[i])
                        }
                        example = tf.train.Example(features=tf.train.Features(feature=feature))

                        if count % 1000 == 0 and count > 0:
                            print("1000")
                            train_writer.close()
                            valid_writer.close()
                            test_writer.close()
                            #sys.stdout.flush()
                            file_group_count += 1

                            train_writer = tf.python_io.TFRecordWriter(
                                out_path + "interval_" + str(interval) + "_label_" + str(
                                    label_name) + "_train_" + str(file_group_count) + ".tfrecords")
                            valid_writer = tf.python_io.TFRecordWriter(
                                out_path + "interval_" + str(interval) + "_label_" + str(
                                    label_name) + "_valid_" + str(file_group_count) + ".tfrecords")
                            test_writer = tf.python_io.TFRecordWriter(
                                out_path + "interval_" + str(interval) + "_label_" + str(
                                    label_name) + "_test_" + str(file_group_count) + ".tfrecords")

                        t = count % 10
                        if t >= 0 and t < 8:
                            train_writer.write(example.SerializeToString())
                        elif t == 8:
                            valid_writer.write(example.SerializeToString())
                        else:
                            test_writer.write(example.SerializeToString())

                        count += 1

                print(count)
                k += 1
                train_writer.close()
                valid_writer.close()
                test_writer.close()
                sys.stdout.flush()

    #制作规定长度的tfrecord
    @staticmethod
    def make_tfrecord_seq_shuffle(interval_list,exp_seq_len,dirname):
        data_dir = "G:/新建文件夹/Geolife Trajectories 1.3/gps_en_discrezation/features_12_95_30/"
        out_path = "G:/all_data/"+dirname
        for interval in interval_list:
            print("处理" + str(interval))
            # train_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_train.tfrecords")
            # valid_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_valid.tfrecords")
            # test_writer = tf.python_io.TFRecordWriter("G:/all_data/tfrecords/interval_"+str(interval)+"_test.tfrecords")
            data_file_name = data_dir + "user_features_data_en_1_interval_" + str(interval) + ".csv"
            data_file = open(data_file_name, mode="r")
            data_df = pd.DataFrame(pd.read_csv(data_file))

            data_label_groups = data_df.groupby(by="label")
            k = 0
            #for label_name, label_group in data_label_groups:

                # if k < 7:
                #     k+=1
                #     continue
                # if k > 3:
                #     return
            file_group_count = 0
            train_writer = tf.python_io.TFRecordWriter(
                out_path + "interval_"+str(interval) + "_train_0.tfrecords")
            valid_writer = tf.python_io.TFRecordWriter(
                out_path + "interval_"+ str(interval)  + "_valid_0.tfrecords")
            test_writer = tf.python_io.TFRecordWriter(
                out_path + "interval_"+ str(interval) + "_test_0.tfrecords")
            seg_groups = data_df.groupby(by="seg_label")
            count = 0
            for seg_name, seg_group in seg_groups:
                if int(seg_group.iloc[0,-3]) > 3:
                    continue

                # seg_group 存放每段的轨迹点的特征，每个特征长30
                speed_sec = np.array(seg_group.iloc[:, 0 : 1 * WIDTH],dtype=np.int64)
                avg_speed = np.array(seg_group.iloc[:, 1* WIDTH : 2 * WIDTH],dtype=np.int64)
                std_speed = np.array(seg_group.iloc[:, 2* WIDTH : 3 * WIDTH],dtype=np.int64)
                acc_sec = np.array(seg_group.iloc[:, 3* WIDTH : 4 * WIDTH],dtype=np.int64)
                mean_acc = np.array(seg_group.iloc[:, 4* WIDTH : 5 * WIDTH],dtype=np.int64)
                std_acc = np.array(seg_group.iloc[:, 5* WIDTH : 6 * WIDTH],dtype=np.int64)
                head = np.array(seg_group.iloc[:, 6* WIDTH : 7 * WIDTH],dtype=np.int64)
                head_mean = np.array(seg_group.iloc[:, 7* WIDTH : 8 * WIDTH],dtype=np.int64)
                std_head = np.array(seg_group.iloc[:, 8* WIDTH : 9 * WIDTH],dtype=np.int64)
                max_speed = np.array(seg_group.iloc[:, 9* WIDTH : 10 * WIDTH],dtype=np.int64)
                max_acc = np.array(seg_group.iloc[:, 10* WIDTH : 11 * WIDTH],dtype=np.int64)
                max_head = np.array(seg_group.iloc[:, 11* WIDTH : 12 * WIDTH],dtype=np.int64)


                speed_sec_pad,speed_sec_early = Data.pad_seqs(speed_sec,exp_seq_len)
                avg_speed_pad,avg_speed_early = Data.pad_seqs(avg_speed,exp_seq_len)
                std_speed_pad,std_speed_early = Data.pad_seqs(std_speed,exp_seq_len)
                acc_sec_pad,acc_sec_early = Data.pad_seqs(acc_sec,exp_seq_len)
                mean_acc_pad,mean_acc_early = Data.pad_seqs(mean_acc,exp_seq_len)
                std_acc_pad,std_acc_early = Data.pad_seqs(std_acc,exp_seq_len)
                head_pad,head_early = Data.pad_seqs(head,exp_seq_len)
                head_mean_pad,head_mean_early = Data.pad_seqs(head_mean,exp_seq_len)
                std_head_pad,std_head_early = Data.pad_seqs(std_head,exp_seq_len)
                max_speed_pad,max_speed_early = Data.pad_seqs(max_speed,exp_seq_len)
                max_acc_pad,max_acc_early = Data.pad_seqs(max_acc,exp_seq_len)
                max_head_pad,max_head_early = Data.pad_seqs(max_head,exp_seq_len)

                label = np.zeros(speed_sec_early.shape,np.int64)
                #print(int(seg_group.iloc[0,-3]))
                label[:] = int(seg_group.iloc[0,-3])

                for i in range(len(speed_sec_early)):
                    start = i*exp_seq_len
                    end = (i+1)*exp_seq_len

                    feature = {
                        param.SPEED_SEC: Data._bytes_feature(speed_sec_pad[start:end].tobytes()),
                        param.AVG_SPEED: Data._bytes_feature(avg_speed_pad[start:end].tobytes()),
                        param.STD_SPEED: Data._bytes_feature(std_speed_pad[start:end].tobytes()),
                        param.ACC_SEC: Data._bytes_feature(acc_sec_pad[start:end].tobytes()),
                        param.MEAN_ACC: Data._bytes_feature(mean_acc_pad[start:end].tobytes()),
                        param.STD_ACC: Data._bytes_feature(std_acc_pad[start:end].tobytes()),
                        param.HEAD: Data._bytes_feature(head_pad[start:end].tobytes()),
                        param.HEAD_MEAN: Data._bytes_feature(head_mean_pad[start:end].tobytes()),
                        param.STD_HEAD: Data._bytes_feature(std_head_pad[start:end].tobytes()),
                        param.MAX_SPEED: Data._bytes_feature(max_speed_pad[start:end].tobytes()),
                        param.MAX_ACC: Data._bytes_feature(max_acc_pad[start:end].tobytes()),
                        param.MAX_HEAD: Data._bytes_feature(max_head_pad[start:end].tobytes()),
                        param.EARLY: Data._int64_feature(std_head_early[i]),
                        param.LABEL: Data._int64_feature(label[i])
                    }
                    example = tf.train.Example(features=tf.train.Features(feature=feature))

                    if count % 1000 == 0 and count > 0:
                        print("1000")
                        train_writer.close()
                        valid_writer.close()
                        test_writer.close()
                        #sys.stdout.flush()
                        file_group_count += 1

                        train_writer = tf.python_io.TFRecordWriter(
                            out_path + "interval_" + str(interval) + "_train_" + str(file_group_count) + ".tfrecords")
                        valid_writer = tf.python_io.TFRecordWriter(
                            out_path + "interval_" + str(interval) + "_valid_" + str(file_group_count) + ".tfrecords")
                        test_writer = tf.python_io.TFRecordWriter(
                            out_path + "interval_" + str(interval) + "_test_" + str(file_group_count) + ".tfrecords")

                    t = count % 10
                    if t >= 0 and t < 8:
                        train_writer.write(example.SerializeToString())
                    elif t == 8:
                        valid_writer.write(example.SerializeToString())
                    else:
                        test_writer.write(example.SerializeToString())

                    count += 1

            print(count)
            k += 1
            train_writer.close()
            valid_writer.close()
            test_writer.close()
            sys.stdout.flush()

    #未完成
    @staticmethod
    def tf_slice_seq(input,exp_len_seq,has_early):

        shape = tf.shape(input)
        full_seq_nums = tf.floordiv(shape[0],exp_len_seq)
        # ?tf.zeros()
        result_list = []
        early_stop = []
        zero_constant = tf.zeros_like(full_seq_nums)
        is_zero = tf.equal(full_seq_nums,zero_constant)
        if not is_zero :
            for i in range(full_seq_nums):
                result_list.append(tf.slice(input,[i*exp_len_seq,WIDTH],[exp_len_seq,WIDTH]))
                if has_early:
                    early_stop.append(exp_len_seq)

        remain_length = shape[0] - full_seq_nums*exp_len_seq
        remain = tf.slice(input,[full_seq_nums*exp_len_seq,WIDTH],[shape[0]-remain_length,WIDTH])
        remain_padding = tf.pad(remain,[[0,exp_len_seq - remain_length],[0,0]])
        result_list.append(remain_padding)
        if has_early:
            early_stop.append(remain_length)

        if has_early:
            e = np.reshape(np.array(early_stop,np.int32),[len(early_stop),1])

            earlys = tf.Constant(e)
            return result_list,earlys

        return result_list

    #未完成
    @staticmethod
    def tf_slice_examples(features,feature_name_list,label_name,has_early,exp_seq_len):

        #feature_sliced_list  [[speed_sec_tensor*full_seq_num]]
        feature_sliced_list = []
        seqs = None
        early_seqs = None
        for feature_name in feature_name_list:
            feature = tf.decode_raw(features[feature_name],tf.int32)
            if has_early:
                seqs,early_seqs = Data.tf_slice_seq(feature,exp_seq_len,has_early)
            else:
                seqs = Data.tf_slice_seq(feature,exp_seq_len, has_early)
            feature_sliced_list.append(seqs)

        if len(feature_sliced_list)>0:
            seq_nums = len(feature_sliced_list[0])
        else:
            return

        features_seqs = None
        for i in range(seq_nums):
            single_seq = None
            for j in range(len[feature_name_list]):
                if single_seq is None:
                    single_seq = feature_sliced_list[i][j]
                else:
                    single_seq = tf.concat([single_seq,feature_sliced_list[i]][j],axis=1)

            single_seq = tf.expand_dims(single_seq,axis=0)
            if features_seqs is None:
                features_seqs = single_seq
            else:
                features_seqs = tf.concat([features_seqs,single_seq],axis=0)

        label = tf.cast(features[label_name], tf.int32)
        label_arr = np.zeros(shape=[seq_nums,1],dtype=tf.int32)
        label_arr[:] = label
        label_seqs = tf.Constant(label_arr,dtype=tf.int32)
        if has_early:
            return features_seqs,early_seqs,label_seqs
        else:
            return features_seqs,label_seqs

if __name__ == "__main__":
    #Data.sovle_row_data(5)
    #Data.caculate_feature([1,2,3,4,5])
    #Data.caculate_feature_max_min()
    #Data.caculate_all_max_min()
    #Data.discretization([1,2,3,4,5])
    #Data.create_npy(2)
    #Data.expand_data_npy(4,100)
    #Data.create_all_data_npy(4,100)
    #Data.concat_data(4,100)
    #Data.make_tfrecord([5])
    #Data.make_tfrecord_seq_shuffle([1,2,3,4,5],50,"tfrecords_95_15/")
    #Data.features_status([5])
    #Data.caculate_feature_12([1,2,3,4,5])
    #Data.discretization_12([1,2,3,4])
    Data.make_tfrecord_seq_shuffle([4], 50, "tfrecords_95_30_12/")