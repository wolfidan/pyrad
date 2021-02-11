
#!/bin/bash
echo "This is a command line tool to help you release new pyart/pyrad version"
echo "Please confirm that you are on master branch and you have added and commit all modifications you want to include in the tag in the master branch!"
echo "Type enter to continue"
read continue

dir=$(dirname "$0")
echo Do you want to release a new pyART version y/n?
read updatepyart
if [[ $updatepyart == "y" ]]; then
echo "Please provide version number, for example 0(major).5(minor).0(micro)"
echo "What is the major version?"
read major
echo "What is the minor version?"
read minor
echo "What is the micro version?"
read micro

cd $dir

echo "Version number is $major.$minor.$micro"
echo "Updating setup.py"
sed -i "/MAJOR =/c\MAJOR = $major" $dir/src/pyrad_proc/setup.py
sed -i "/MINOR =/c\MINOR = $minor" $dir/src/pyrad_proc/setup.py
sed -i "/MICRO =/c\MICRO = $micro" $dir/src/pyrad_proc/setup.py

echo "Updating /doc/source/conf.py"
sed -i "/version = u/c\version = u'$major.$minor'" $dir/doc/source/conf.py
sed -i "/release = u/c\release = u'$major.$minor.$micro'" $dir/doc/source/conf.py

echo "Done!"
echo "We will now push the version number updated on github"
git add --all
git commit -m "Changed version numbers"
git push origin master

echo "Do you want to push the new tag on github? y/n"
read pushtag
if [[ $pushtag == "y" ]]; then
git tag "v${major}.${minor}"
git push origin "v${major}.${minor}"
fi
echo "Done!"

echo "Do you want to create a new PyPI (pip) package? y/n"
read releasepypi
if [[ $releasepypi == "y" ]]; then
python setup.py sdist
echo "Should it be a test package or a final (official) package? test/final"
read pkgtype
if [[ $pkgtype == "test" ]]; then
python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
fi
if [[ $pkgtype == "final" ]]; then
python -m twine upload dist/*
fi
fi
echo "Done!"
fi


echo Do you want to release a new pyRAD version y/n?
read updatepyrad
if [[  "$updatepyrad" == "y" ]]; then
echo "Please provide version number, for example 0(major).5(minor).0(micro)"
echo "What is the major version?"
read major
echo "What is the minor version?"
read minor
echo "What is the micro version?"
read micro

cd $dir/

echo "Version number is $major.$minor.$micro"
echo "Updating setup.py"
sed -i "/MAJOR =/c\MAJOR = $major" $dir/src/pyrad_proc/setup.py
sed -i "/MINOR =/c\MINOR = $minor" $dir/src/pyrad_proc/setup.py
sed -i "/MICRO =/c\MICRO = $micro" $dir/src/pyrad_proc/setup.py

echo "Updating /doc/source/conf.py"
sed -i "/version = u/c\version = u'$major.$minor'" ./doc/source/conf.py
sed -i "/release = u/c\release = u'$major.$minor.$micro'" ./doc/source/conf.py

echo "We will now push the version number updated on github"
git add --all
git commit -m "Changed version numbers"
git push origin master

echo "Done!"
echo "Do you want to push the new tag on github? y/n"
read pushtag
if [[ $pushtag == "y" ]]; then
git tag "v${major}.${minor}"
git push origin "v${major}.${minor}"
fi

echo "Do you want to create a new PyPI (pip) package? y/n"
read releasepypi
if [[ $releasepypi == "y" ]]; then
python setup.py sdist
echo "Should it be a test package or a final (official) package? test/final"
read pkgtype
if [[ $pkgtype == "test" ]]; then
python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*
fi
if [[ $pkgtype == "final" ]]; then
python -m twine upload dist/*
fi
fi

fi

fi