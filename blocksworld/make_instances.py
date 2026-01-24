import random
import math
import argparse as ap

def gridToLin(blockList, blockNums):
    lin = [0 for i in range(blockNums)]
    for i in blockList:
        for j in range(len(i)):
            onBlock = i[j-1]
            if j==0:
                lin[i[j]] = 0
            else:
                lin[i[j]] = onBlock+1
    return lin

def generateTableWrapper(blocks):
    table = generateTable(blocks, random.randrange(1,math.floor(math.sqrt(blocks))))
    return gridToLin(table,blocks)

def generateTable(blocks, stacks):
    blockStorage = [i for i in range(blocks)]
    grid = [[] for i in range(stacks)]
    blocksLeft = blocks
    for i in range(blocks):
        grid[random.randrange(stacks)].append(blockStorage.pop(random.randrange(blocksLeft)))
        blocksLeft-=1
    return grid

def adjacencies(lst):
    blocks = len(lst)
    above = [None] * blocks
    below = [None] * blocks
    for i in range(blocks):
        blockInfo = lst[i]
        if blockInfo == 0:
            below[i] = None
        else:
            blockInfo -= 1
            below[i] = blockInfo
            above[blockInfo] = i
    return above,below

def writePuzzle(start, goal, fileName = "newPuzzle.txt"):
    writeFile = open(fileName,"w")
    writeFile.write(str(len(start))+"\nWhat each block is on:\n")
    for i in start:
        writeFile.write(str(i)+"\n")
    writeFile.write("Goal:\n")
    for i in goal:
        writeFile.write(str(i)+"\n")
    writeFile.close()

def main(blocks, testName = "newPuzzle.txt", startStacks = None, endStacks = None):
    if startStacks==None:
        startTable = generateTableWrapper(blocks)
    else:
        startTable = gridToLin(generateTable(blocks, int(startStacks)),blocks)
    if  endStacks==None:
        goalTable = generateTableWrapper(blocks)
    else:
        goalTable =  gridToLin(generateTable(blocks, int(endStacks)),blocks)
    writePuzzle(startTable, goalTable, testName)

if __name__=="__main__":
    argParser = ap.ArgumentParser(description = 'Create a Blocksworld puzzle. Use both -b and -f to create a new puzzle with b blocks, and write to file f.')
    argParser.add_argument('-b', type = int, help = "Number of blocks in the puzzle.")
    argParser.add_argument('-f', type = str, help = "Name of input file/name of new puzzle")
    argParser.add_argument('-ss', type = int, help = "Number of stacks in the start puzzle.")
    argParser.add_argument('-sg', type = int, help = "Number of stacks in the goal state.")
    arguments = argParser.parse_args()

    problem = "generatedProblem.txt"
    blocks = 9

    if arguments.b!=None:
        blocks = int(arguments.b)
    if arguments.f != None:
        problem = arguments.f
    main(blocks, problem, arguments.ss, arguments.sg)
