// class SuperTask {
//     constructor(poolSize){
//         this.poolSize = poolSize
//         this.waitingTasks = []
//         this.runningTaskCount = 0
//     }
//     setPoolSize(size){
//         this.poolSize = size
//         this.runTask()
//     }
//     add(task){
//         return new Promise(resolve=>{
//             this.waitingTasks.push([task,resolve])
//             this.runTask()
//         })

//     }
//     runTask(){
//         if(this.runningTaskCount<this.poolSize && this.waitingTasks.length > 0){
//             const [task,resolve] = this.waitingTasks.shift()
//             this.runningTaskCount++
//             task().then(()=>{
//                 resolve()
//                 this.runningTaskCount--
//                 this.runTask()
//             })
//         }
//     }
// }

// const superTask = new  SuperTask(2)
// function addTask(time,name){
//     const label = `任务 ${name},完成`
//     console.time(label)
//     superTask.add(()=>timeout(time)).then(()=>console.timeEnd(label))
// }
// const timeout = time=>new Promise(resolve=>setTimeout(resolve,time))

// addTask(10000,1)
// addTask(5000,2)
// addTask(3000,3)
// addTask(4000,4)
// addTask(5000,5)
// setTimeout(()=>superTask.setPoolSize(5),7000)

// function flatArray(arr){
//     let res = []
//     for(const item of arr) {
//         if(Array.isArray(item)){
//             res = res.concat(flatArray(item))
//         }
//         else res.push(item)
//     }
//     return res
// }
// const arr = [[1,2],[3,4,5],[6,7,[8,9,10]]]

// console.log(flatArray(arr))

// function deepClone(obj){
//     if(typeof ojb !=='object' && obj!=null){
//         return obj
//     }
//     let newObj
//     if(Array.isArray(obj)) {
//         newObj = []
//         for(const item of obj) {
//             newObj.push(deepClone(item))
//         }
//     }
//     if(obj instanceof Map) {
//         newObj = new Map([...obj])
//     }
//     if(obj instanceof Set) {
//         newObj = new Set([...obj])
//     }
//     else {
//         newObj = {}
//         Reflect.ownKeys(obj).forEach(key=>{
//             newObj[key] = deepClone(obj[key])
//         })
//     }
//     return newObj
// }

// const obj = {a:function(){console.log(111)}}
// deepClone(obj)

// function hasCircularReference(obj,visited=new WeakSet()){
//     if(obj && typeof obj == 'object'){
//         if(visited.has(obj))
//             return true

//     visited.add(obj)
//     Reflect.ownKeys(obj).forEach(key=>{
//         if(hasCircularReference(obj[key],visited)){
//             return true
//         }
//     })
//     visited.delete(obj)
//     }
//     return false
// }

// const curry = (fn)=>{
//     let params = []
//     const curried = (args)=>{
//         if(args.length <= 0) {
//             const allParams = params
//             params = []
//             return fn(...allParams)
//         }
//         params = [...params,...args]
//         return curried
//     }
//     return curried
// }

// const reverseStr = str=>{
//     return Array.from(str).reduce((pre,cur)=> `${cur}${pre}`,'')
// }

// function debounce(fn,delay){
//     let timer
//     return (...args) =>{
//       timer && clearTimeout(timer)
//         timer = setTimeout(()=>{
//             fn(args)
//             timer = null
//         },delay)

//     }
// }

// function throttle(fn,delay) {
//     let timer

//     return (...args)=>{
//         if(timer) return
//         timer = setTimeout(()=>{
//             fn(...args)
//             timer = null
//         },delay)
//     }
// }

// const uploadImg = (img)=>new Promise(resolve=>{
//     setTimeout(()=>{
//         resolve(img)
//     },3000*Math.random())
// })

// const warpResult = (imgList)=>{
//     const resultMap = {}
//     imgList.forEach(img=>resultMap[img] = false)

//     let index  = 0

//     return new Promise(resolve=>{
//         const download = ()=>{
//             if(index >= imgList.length) {
//                 if(!Object.keys(resultMap).find(resultMap[keys] == false)) {
//                     resolve(resultMap)
//                 }
//                 return
//             }

//             uploadImg(imgList[index]).then((res)=>{
//                 resultMap[imgList[index]] = res
//                 setTimeout(download,100)
//             })
//             ++index
//         }
//         while(index <= 5){
//             download()
//         }
//     })

// }

// const downloadImage = (src,imgName)=>{
//     const image =new Image()
//     image.src = src
//     image.setAttribute('crossOrigin','anonymous')
//     image.onload = function(){
//         let c = document.createElement('canvas')
//         c.width = image.width
//         c.height = image.height
//         c.getContext('2d').drawImage(image,0,0,image.width,image.height)
//         let a = document.createElement('a')
//         a.download=imgName
//         a.href = c.toDataURL('image/png')
//         a.click()
//     }
// }

// class Component {
//   _data = { name: "" };
//   pending = false;

//   constructor() {
//     this.data = new Proxy(this._data, {
//       set: (target, key, value) => {
//         this._data[key] = value;
//         if (!this.pending) {
//           this.pending = true;
//           Promise.resolve().then(() => {
//             this.pending = false;
//             this.render();
//           });
//         }
//       },
//     });
//   }

//   render() {
//     console.log("render", this._data.name);
//   }
// }

// const com = new Component();
// com.data.name = "1";
// com.data.name = "2";
// setTimeout(() => {
//   com.data.name = "timeout";
// }, 0);

// function set(obj, keyPath, value) {
//   const currentKey = keyPath.shift();
//   if (keyPath.length == 0) {
//     obj[currentKey] = value;
//   } else {
//     set(obj[currentKey], keyPath, value);
//   }
// }

// function myInstanceOf(left, right) {
//   let proto = Object.getPrototypeOf(left);
//   const prototype = right.prototype;
//   while (true) {
//     if (!proto) return false;
//     if (proto == prototype) return true;

//     proto = Object.getPrototypeOf(proto);
//   }
// }

// function myNew() {
//   let newObj = null;
//   const constructor = Array.prototype.shift.call(arguments);
//   let result;

//   if (typeof constructor !== "function") {
//     console.error("type error");
//     return;
//   }

//   newObj = Object.create(constructor.prototype);
//   result = constructor.apply(newObj, arguments);
//   let flag =
//     result && (typeof result == "object" || typeof result == "function");
//   return flag ? result : newObj;
// }

// function promiseAll(list) {
//   return new Promise((resolve, reject) => {
//     if (!Array.isArray(list)) {
//       throw new TypeError("argument must be a array");
//     }

//     const len = list.length;
//     let count = 0;
//     const res = new Array(len).fill(0);

//     for (let i = 0; i < len; i++) {
//       Promise.resolve(list[i]).then((res) => {
//         count++;
//         res[i] = res;
//         if (count == len) {
//           resolve(res);
//           return;
//         }
//       },error=>reject(error));
//     }

//   });
// }

// function PromiseRace(list) {
//     return new Promise((resolve,reject)=>{
//         for(let i = 0; i<list.length; i++){
//             list[i].then(resolve,reject)
//         }
//     })
// }


// function getType(value){
//     if(value === null) return '' + value
//     if(typeof value == 'object') {
//         let valueClass = Object.prototype.toString.call(value)
//         const type = valueClass.split(' ')[1].split('').pop()
//         return type.join('').toLowerCase()
//     }else {
//         return typeof value
//     }
// }

// Function.prototype.myCall = function(context) {
//     if(typeof this !== 'function') {
//         throw new TypeError('this must be function')
//     }

//     let args = [...arguments].slice(1)
//     context = context || window
//     context.fn = this
//     const result = context.fn(args)
//     delete context.fn
//     return result
// }

// Function.prototype.myApply =  function(context) {
//     if(typeof this !== 'function') {
//         throw new TypeError('this must be function')
//     } 
//     context = context || window
//     context.fn = this
//     let result = null

//     if(arguments[1]){
//         result = context.fn(...arguments[1])
//     }else {
//         result = context.fn()
//     }

//     delete context.fn
    
//     return result
        
// }

// Function.prototype.myBind = function(context) {
//     if(typeof this !== 'function'){
//         throw new TypeError('error')
//     }
//     const fn = this
//     context = context || window
//     const args = [...arguments].slice(1)

//     return function Fn(){
//         return fn.apply(this instanceof Fn ? this : context, args.concat([...arguments]))        
//     }
// }


// function format(n){
//     if(n.length<=3) return n
//     const len = n.length
//     const remainder = n%3

//     if(remainder > 0) {
//         return n.slice(0,remainder) + ',' + n.slice(remainder,len).match(/\d{3}/g).join(',')
//     }
//     return n.slice(0,len).match(/\d{3}/g).join(',')

// }


// function sumBigNumber(a,b){
//     let i = a.length-1
//     let j = b.length-1
//     let carry=0
//     let res = ''
//     while(i>=0||j>=0||carry) {
//         const digitA = i>=0? Number(a[i]):0
//         const digitB = j>=0? Number(b[j]):0
//         const sum = digitA+digitB+carry
//         res = (sum%10)+res
//         carry = Math.floor(sum/10)
//         i--
//         j--
//     }
//     return res
// }

// function multiplyBigNumber(a,b){
//     if(a=='0'||b=='0') return '0'

//     const aArr = a.split('').reverse().map(Number)
//     const bArr = b.split('').reverse().map(Number)

//     const aLen = a.length
//     const bLen = b.length

//     const result = new Array(aLen+bLen).fill(0)

//     for(let i = 0; i< aLen; i++){
//         for(let j = 0;j<bLen;j++){
//             result[i+j] += aArr[i] * bArr[j]
//         }
//     }
//     let carry = 0

//     for(let i = 0; i<result.length;i++){
//         const sum = result[i] +carry
//         result[i] = sum %10
//         carry = Math.floor(sum/10)
//     }

//     while(result.length && result[result.length-1] == 0){
//         result.pop()
//     }

//     return result.reverse().join('')

// }


// console.log(multiplyBigNumber('123', '456')); // "56088"
// console.log(multiplyBigNumber('999', '999')); // "998001"
// console.log(multiplyBigNumber('0', '12345')); // "0"

// function buildTree(node,list){
//     const children = list.filter(i=>i.pid == node.id)
//     node.children = children.map(i=>buildTree(i,list))
//     return node
// }

function red() {
    console.log('red');
}
function green() {
    console.log('green');
}
function yellow() {
    console.log('yellow');
}

function task(light,time) {
    return new Promise(resolve=>{
        setTimeout(()=>{
            if(light == 'yellow'){
                yellow()
            }
            if(light == 'green'){
                green()
            }
            if(light =='red'){
                red()
            }
            resolve()
        },time)
    })
}
function step(){
    task('red',3000)
    .then(()=>task('green',2000))
    .then(()=>task('yellow',2100))
    .then(step)
}

step()

function childNum(num,count){
    const all = []
    for(let i = 0;i<num;i++){
        all[i]= i+1
    }
    let exitCount = 0
    let counter = 0
    let currentIndex = 0

    while(exitCount < num-1) {
        if(all[currentIndex] !== 0) count++

        if(counter = count) {
            all[currentIndex] = 0
            exitCount++
            counter = 0
        }

        currentIndex++
        if(currentIndex == num) {
            currentIndex = 0
        }

        for(i=0;i<num;i++){
            if(all[i] !=0) return a[i]
        }
    }
}


function longestSubStrLen(s){
    let map = new Map()
    let i = -1
    let res = 0
    for(let j = 0;j<s.length;j++){
        if(map.has(s[j])){
            i = Math.max(i,map.get(s[j]))
        }
        res = Math.max(res,j-i)
        map.set(s[j],j)
    }
}

function longestSubString(s) {
    let max = 0
    const arr = []
    for(let i = 0;i<s.length;i++){
        const sameIndex = arr.findIndex(item=>item == s[i])
        arr.push(s[i])
        if(sameIndex>=0){
            arr.splice(sameIndex+1)
        }
        max = Math.max(max,arr.length)
    }
    return max
}